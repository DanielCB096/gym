from collections.abc import Iterator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user


def test_authentication_and_permission_guards_are_enforced_by_api() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="reception@example.com",
            password="correct-horse-battery-staple",
            role_codes=("reception",),
        )
        register_user(
            session,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            assert client.get("/admin/staff").status_code == 401
            assert client.post(
                "/auth/login",
                json={"email": "reception@example.com", "password": "wrong-password"},
            ).status_code == 401

            reception_login = client.post(
                "/auth/login",
                json={"email": "reception@example.com", "password": "correct-horse-battery-staple"},
            )
            assert reception_login.status_code == 200
            reception_token = reception_login.json()["access_token"]
            reception_headers = {"Authorization": f"Bearer {reception_token}"}

            assert client.get("/admin/staff", headers=reception_headers).status_code == 403
            assert client.get("/admin/roles", headers=reception_headers).status_code == 403
            assert client.get("/admin/users", headers=reception_headers).status_code == 403

            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-correct-horse-battery"},
            )
            assert owner_login.status_code == 200
            owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
            assert client.get("/admin/roles", headers=owner_headers).status_code == 200
            owner_users = client.get("/admin/users", headers=owner_headers)
            assert owner_users.status_code == 200
            assert [user["email"] for user in owner_users.json()] == [
                "owner@example.com",
                "reception@example.com",
            ]
            assert owner_users.json()[0]["roles"] == ["owner"]
            created_employee = client.post(
                "/admin/staff",
                headers=owner_headers,
                json={
                    "employee_number": "RC-1001",
                    "first_name": "Lucía",
                    "last_name": "Mendoza",
                    "email": "lucia@example.com",
                    "job_title": "Recepción",
                },
            )
            assert created_employee.status_code == 201
            assert len(client.get("/admin/staff", headers=owner_headers).json()) == 1

            created_user = client.post(
                "/admin/users",
                headers=owner_headers,
                json={
                    "email": "lucia@example.com",
                    "password": "lucia-strong-preview-password",
                    "employee_id": created_employee.json()["id"],
                    "role_codes": ["reception"],
                },
            )
            assert created_user.status_code == 201
            assert created_user.json()["roles"] == ["reception"]

            users_after_creation = client.get("/admin/users", headers=owner_headers).json()
            lucia = next(user for user in users_after_creation if user["email"] == "lucia@example.com")
            assert lucia["employee_id"] == created_employee.json()["id"]
            assert lucia["employee_name"] == "Lucía Mendoza"
            assert lucia["roles"] == ["reception"]
            assert lucia["status"] == "active"

            cannot_remove_last_owner = client.delete(
                f"/admin/users/{owner_login.json()['user']['id']}/roles/owner",
                headers=owner_headers,
            )
            assert cannot_remove_last_owner.status_code == 409

            assert client.post("/auth/logout", headers=reception_headers).status_code == 204
            assert client.get("/admin/staff", headers=reception_headers).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_session_administration_lists_and_revokes_sessions() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )
        register_user(
            session,
            email="reception@example.com",
            password="correct-horse-battery-staple",
            role_codes=("reception",),
        )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner_token = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-correct-horse-battery"},
            ).json()["access_token"]
            owner_headers = {"Authorization": f"Bearer {owner_token}"}
            reception_token = client.post(
                "/auth/login",
                json={"email": "reception@example.com", "password": "correct-horse-battery-staple"},
            ).json()["access_token"]
            reception_headers = {"Authorization": f"Bearer {reception_token}"}

            assert client.get("/admin/sessions", headers=reception_headers).status_code == 403

            listed = client.get("/admin/sessions", headers=owner_headers)
            assert listed.status_code == 200
            sessions = listed.json()
            assert {item["email"] for item in sessions} == {"owner@example.com", "reception@example.com"}
            current = [item for item in sessions if item["is_current"]]
            assert len(current) == 1
            assert current[0]["email"] == "owner@example.com"

            reception_session_id = next(
                item["id"] for item in sessions if item["email"] == "reception@example.com"
            )
            assert client.delete(
                f"/admin/sessions/{reception_session_id}", headers=owner_headers
            ).status_code == 204
            assert client.get("/auth/me", headers=reception_headers).status_code == 401

            remaining = client.get("/admin/sessions", headers=owner_headers).json()
            assert {item["email"] for item in remaining} == {"owner@example.com"}

            assert client.delete(f"/admin/sessions/{uuid4()}", headers=owner_headers).status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_staff_and_account_creation_guards() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )
        register_user(
            session,
            email="reception@example.com",
            password="correct-horse-battery-staple",
            role_codes=("reception",),
        )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'email': 'owner@example.com', 'password': 'owner-correct-horse-battery'}).json()['access_token']}"
            }
            reception_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'email': 'reception@example.com', 'password': 'correct-horse-battery-staple'}).json()['access_token']}"
            }

            employee_payload = {
                "employee_number": "RC-2001",
                "first_name": "Ana",
                "last_name": "Ruiz",
                "job_title": "Gerencia",
                "email": "ana@example.com",
            }
            # Reception cannot create staff or accounts.
            assert client.post("/admin/staff", json=employee_payload, headers=reception_headers).status_code == 403
            assert client.post(
                "/admin/users",
                json={"email": "ana@example.com", "password": "ana-strong-password-1", "role_codes": ["manager"]},
                headers=reception_headers,
            ).status_code == 403

            created = client.post("/admin/staff", json=employee_payload, headers=owner_headers)
            assert created.status_code == 201
            employee_id = created.json()["id"]
            # Duplicate employee number or email is rejected.
            assert client.post("/admin/staff", json=employee_payload, headers=owner_headers).status_code == 409
            assert client.post(
                "/admin/staff",
                json={**employee_payload, "employee_number": "RC-2002", "email": "ana@example.com"},
                headers=owner_headers,
            ).status_code == 409

            # Short password is rejected before reaching the service.
            assert client.post(
                "/admin/users",
                json={"email": "ana@example.com", "password": "short", "role_codes": ["manager"]},
                headers=owner_headers,
            ).status_code == 422
            # Unknown role, missing employee and duplicate account email are rejected.
            assert client.post(
                "/admin/users",
                json={"email": "ana@example.com", "password": "ana-strong-password-1", "role_codes": ["does-not-exist"]},
                headers=owner_headers,
            ).status_code == 409
            assert client.post(
                "/admin/users",
                json={
                    "email": "ana@example.com",
                    "password": "ana-strong-password-1",
                    "employee_id": str(uuid4()),
                    "role_codes": ["manager"],
                },
                headers=owner_headers,
            ).status_code == 409

            account = client.post(
                "/admin/users",
                json={
                    "email": "ana@example.com",
                    "password": "ana-strong-password-1",
                    "employee_id": employee_id,
                    "role_codes": ["manager"],
                },
                headers=owner_headers,
            )
            assert account.status_code == 201, account.text
            assert account.json()["roles"] == ["manager"]
            assert account.json()["employee_id"] == employee_id
            assert client.post(
                "/admin/users",
                json={"email": "ana@example.com", "password": "ana-strong-password-2", "role_codes": ["reception"]},
                headers=owner_headers,
            ).status_code == 409
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_user_account_status_administration() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )
        register_user(
            session,
            email="reception@example.com",
            password="correct-horse-battery-staple",
            role_codes=("reception",),
        )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'email': 'owner@example.com', 'password': 'owner-correct-horse-battery'}).json()['access_token']}"
            }
            reception_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'email': 'reception@example.com', 'password': 'correct-horse-battery-staple'}).json()['access_token']}"
            }
            reception_id = client.get("/auth/me", headers=reception_headers).json()["id"]
            owner_id = client.get("/auth/me", headers=owner_headers).json()["id"]

            # Only accounts with roles.manage may change the status.
            assert client.patch(
                f"/admin/users/{reception_id}", json={"status": "disabled"}, headers=reception_headers
            ).status_code == 403
            # The status must be one of the allowed values.
            assert client.patch(
                f"/admin/users/{reception_id}", json={"status": "suspended"}, headers=owner_headers
            ).status_code == 422
            # Unknown accounts are not found.
            assert client.patch(
                f"/admin/users/{uuid4()}", json={"status": "disabled"}, headers=owner_headers
            ).status_code == 404

            disabled = client.patch(
                f"/admin/users/{reception_id}", json={"status": "disabled"}, headers=owner_headers
            )
            assert disabled.status_code == 200
            assert disabled.json()["status"] == "disabled"
            # Disabling revokes the open session immediately...
            assert client.get("/auth/me", headers=reception_headers).status_code == 401
            # ...and blocks new logins.
            assert client.post(
                "/auth/login",
                json={"email": "reception@example.com", "password": "correct-horse-battery-staple"},
            ).status_code == 401

            # The last active owner cannot be disabled.
            assert client.patch(
                f"/admin/users/{owner_id}", json={"status": "disabled"}, headers=owner_headers
            ).status_code == 409

            enabled = client.patch(
                f"/admin/users/{reception_id}", json={"status": "active"}, headers=owner_headers
            )
            assert enabled.status_code == 200
            assert enabled.json()["status"] == "active"
            # Re-enabling does not resurrect the revoked session but allows a new login.
            assert client.get("/auth/me", headers=reception_headers).status_code == 401
            assert client.post(
                "/auth/login",
                json={"email": "reception@example.com", "password": "correct-horse-battery-staple"},
            ).status_code == 200
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_role_permission_administration_guards() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-correct-horse-battery",
            role_codes=("owner",),
        )
        register_user(
            session,
            email="reception@example.com",
            password="correct-horse-battery-staple",
            role_codes=("reception",),
        )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'email': 'owner@example.com', 'password': 'owner-correct-horse-battery'}).json()['access_token']}"
            }
            reception_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'email': 'reception@example.com', 'password': 'correct-horse-battery-staple'}).json()['access_token']}"
            }

            # Reception lacks roles.manage.
            assert client.post(
                "/admin/roles/reception/permissions",
                json={"permission_code": "payroll.read"},
                headers=reception_headers,
            ).status_code == 403
            assert client.delete(
                "/admin/roles/reception/permissions/inventory.read", headers=reception_headers
            ).status_code == 403

            # Granting and revoking changes the effective matrix.
            assert client.post(
                "/admin/roles/reception/permissions",
                json={"permission_code": "payroll.read"},
                headers=owner_headers,
            ).status_code == 204
            roles = client.get("/admin/roles", headers=owner_headers).json()
            reception = next(role for role in roles if role["code"] == "reception")
            assert "payroll.read" in reception["permissions"]

            assert client.delete(
                "/admin/roles/reception/permissions/payroll.read", headers=owner_headers
            ).status_code == 204
            roles = client.get("/admin/roles", headers=owner_headers).json()
            reception = next(role for role in roles if role["code"] == "reception")
            assert "payroll.read" not in reception["permissions"]

            # The owner role is protected.
            assert client.post(
                "/admin/roles/owner/permissions",
                json={"permission_code": "payroll.read"},
                headers=owner_headers,
            ).status_code == 409
            assert client.delete(
                "/admin/roles/owner/permissions/settings.manage", headers=owner_headers
            ).status_code == 409

            # Unknown roles and permissions are not found.
            assert client.post(
                "/admin/roles/ghost/permissions",
                json={"permission_code": "payroll.read"},
                headers=owner_headers,
            ).status_code == 404
            assert client.post(
                "/admin/roles/reception/permissions",
                json={"permission_code": "ghost.read"},
                headers=owner_headers,
            ).status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()