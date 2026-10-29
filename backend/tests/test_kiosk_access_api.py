from collections.abc import Iterator
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.access import kiosk as kiosk_module
from app.modules.access.kiosk import (
    ACCESS_CODE_MAX_REQUESTS,
    KIOSK_TOKEN_LIFETIME,
    InvalidAccessCode,
    InvalidKioskToken,
    authenticate_kiosk_device,
    check_in_with_code,
    create_kiosk_device,
    issue_member_access_code,
    latest_member_access_code_status,
)
from app.modules.access.models import (
    AccessDecision,
    AccessDirection,
    AccessReason,
    AccessWindow,
    KioskAttempt,
    KioskDevice,
    utc_now,
)
from app.modules.access.service import (
    count_member_entries_today,
    last_member_entry_at,
    read_antipassback_seconds,
    record_access_event,
    replace_plan_access_windows,
    update_antipassback_seconds,
)
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan


def _build_engine():
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

    return engine


def _seed(session: Session) -> dict[str, UUID]:
    ensure_default_access_control(session)
    register_user(
        session,
        email="owner@example.com",
        password="owner-strong-password",
        role_codes=("owner",),
    )
    register_user(
        session,
        email="reception@example.com",
        password="reception-strong-password",
        role_codes=("reception",),
    )
    now = datetime.now(timezone.utc)
    plan = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=50000)
    ana = Member(first_name="Ana", last_name="Lopez", email="ana@example.com", status="active")
    beto = Member(first_name="Beto", last_name="Ruiz", email="beto@example.com", status="active")
    lapsed = Member(first_name="Carla", last_name="Soto", email="carla@example.com", status="active")
    session.add_all([plan, ana, beto, lapsed])
    session.flush()
    session.add_all(
        [
            Membership(
                member_id=ana.id,
                plan_id=plan.id,
                status="active",
                starts_at=now - timedelta(days=10),
                ends_at=now + timedelta(days=20),
            ),
            Membership(
                member_id=beto.id,
                plan_id=plan.id,
                status="active",
                starts_at=now - timedelta(days=40),
                ends_at=now - timedelta(days=1),
            ),
            Membership(
                member_id=lapsed.id,
                plan_id=plan.id,
                status="active",
                starts_at=now + timedelta(days=5),
                ends_at=now + timedelta(days=35),
            ),
        ]
    )
    session.commit()
    return {"ana": ana.id, "beto": beto.id, "carla": lapsed.id, "plan": plan.id}


def _login_staff(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _login_member(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    verified = client.post(
        "/member/auth/verify",
        json={"email": email, "code": requested.json()["preview_code"]},
    )
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _create_device(client: TestClient, headers: dict[str, str], label: str = "Recepción"):
    response = client.post("/admin/kiosk/devices", headers=headers, json={"label": label})
    assert response.status_code == 201, response.text
    return response.json()


def _wrong_code(valid: str, index: int) -> str:
    candidate = f"{(index + 1) % 1_000_000:06d}"
    return candidate if candidate != valid else f"{(index + 500_000) % 1_000_000:06d}"


def test_kiosk_device_provisioning_and_code_check_in(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            assert client.get("/admin/kiosk/devices").status_code == 401

            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            reception = _login_staff(client, "reception@example.com", "reception-strong-password")

            assert client.get("/admin/kiosk/devices", headers=reception).status_code == 403
            empty = client.get("/admin/kiosk/devices", headers=owner)
            assert empty.status_code == 200
            assert empty.json() == {"items": []}

            assert client.post(
                "/admin/kiosk/devices", headers=owner, json={"label": ""}
            ).status_code == 422
            assert client.post(
                "/admin/kiosk/devices", headers=owner, json={"label": "   "}
            ).status_code == 422
            assert client.post(
                "/admin/kiosk/devices", headers=reception, json={"label": "Recepción"}
            ).status_code == 403

            device = _create_device(client, owner)
            token = device["token"]
            assert device["status"] == "active"
            assert device["last_seen_at"] is None
            assert len(token) >= 32
            assert "token" not in client.get("/admin/kiosk/devices", headers=owner).json()["items"][0]

            with Session(engine) as session:
                stored = session.exec(select(KioskDevice)).one()
                assert stored.token_sha256 == sha256(token.encode("utf-8")).hexdigest()
                assert stored.token_sha256 != token

            member_headers = _login_member(client, "ana@example.com")
            first = client.post("/member/access/code", headers=member_headers)
            assert first.status_code == 201, first.text
            first_body = first.json()
            assert len(first_body["code"]) == 6 and first_body["code"].isdigit()
            assert first_body["expires_in_seconds"] == 300
            expires_at = datetime.fromisoformat(first_body["expires_at"])
            assert expires_at > datetime.now(timezone.utc) + timedelta(minutes=4)

            second = client.post("/member/access/code", headers=member_headers)
            assert second.status_code == 201
            code = second.json()["code"]

            kiosk_headers = {"X-Kiosk-Token": token}
            assert client.post("/kiosk/check-in", json={"code": code}).status_code == 401
            assert client.post(
                "/kiosk/check-in",
                headers={"X-Kiosk-Token": "not-a-token"},
                json={"code": code},
            ).status_code == 401

            superseded = client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": first_body["code"]}
            )
            assert superseded.status_code == 400

            granted = client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": code}
            )
            assert granted.status_code == 200, granted.text
            granted_body = granted.json()
            assert granted_body["authorized"] is True
            assert granted_body["reason"] == "entry_allowed"
            assert granted_body["message"] == "Acceso concedido"
            assert granted_body["member_name"] == "Ana L."
            assert granted_body["reader_id"] == "Kiosco Recepción"
            UUID(granted_body["event_id"])

            assert client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": code}
            ).status_code == 400
            assert client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": "12ab"}
            ).status_code == 400

            events = client.get("/admin/access-events", headers=owner).json()
            assert events["total"] == 1
            event = events["items"][0]
            assert event["authorized"] is True
            assert event["source"] == "reader"
            assert event["reader_id"] == "Kiosco Recepción"
            assert event["member_name"] == "Ana Lopez"

            revoked = client.post(
                f"/admin/kiosk/devices/{device['id']}/revoke",
                headers=owner,
            )
            assert revoked.status_code == 200
            assert revoked.json()["status"] == "revoked"

            refreshed = client.post("/member/access/code", headers=member_headers)
            assert refreshed.status_code == 201
            assert client.post(
                "/kiosk/check-in",
                headers=kiosk_headers,
                json={"code": refreshed.json()["code"]},
            ).status_code == 401

            assert client.post(
                f"/admin/kiosk/devices/{device['id']}/revoke",
                headers=reception,
            ).status_code == 403
            assert client.post(
                "/admin/kiosk/devices/00000000-0000-0000-0000-000000000000/revoke",
                headers=owner,
            ).status_code == 404

            listed = client.get("/admin/kiosk/devices", headers=owner).json()["items"]
            assert len(listed) == 1
            assert listed[0]["status"] == "revoked"
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_member_access_code_status_tracks_consumption(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            assert client.get("/member/access/code").status_code == 401

            with Session(engine) as session:
                assert latest_member_access_code_status(session, ids["ana"]).status == "none"

            member_headers = _login_member(client, "ana@example.com")
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            device = _create_device(client, owner)
            kiosk_headers = {"X-Kiosk-Token": device["token"]}

            issued = client.post("/member/access/code", headers=member_headers)
            assert issued.status_code == 201, issued.text
            code = issued.json()["code"]

            active = client.get("/member/access/code", headers=member_headers)
            assert active.status_code == 200, active.text
            active_body = active.json()
            assert active_body["status"] == "active"
            assert active_body["consumed_at"] is None
            assert datetime.fromisoformat(active_body["issued_at"]) <= datetime.now(
                timezone.utc
            )
            assert (
                datetime.fromisoformat(active_body["expires_at"])
                == datetime.fromisoformat(issued.json()["expires_at"])
            )

            granted = client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": code}
            )
            assert granted.status_code == 200, granted.text
            assert granted.json()["authorized"] is True

            consumed = client.get("/member/access/code", headers=member_headers).json()
            assert consumed["status"] == "consumed"
            assert datetime.fromisoformat(consumed["consumed_at"]) > datetime.fromisoformat(
                consumed["issued_at"]
            )

            refreshed = client.post("/member/access/code", headers=member_headers)
            assert refreshed.status_code == 201
            assert (
                client.get("/member/access/code", headers=member_headers).json()["status"]
                == "active"
            )

            with Session(engine) as session:
                later = latest_member_access_code_status(
                    session, ids["ana"], now=utc_now() + timedelta(minutes=6)
                )
            assert later.status == "expired"
            assert later.consumed_at is None
            assert later.expires_at is not None
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_member_access_code_status_reports_daily_consumption(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)
        plan = session.get(Plan, ids["plan"])
        plan.daily_entry_limit = 2
        session.add(plan)
        session.commit()

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            member_headers = _login_member(client, "ana@example.com")
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            device = _create_device(client, owner)
            kiosk_headers = {"X-Kiosk-Token": device["token"]}

            # Sin códigos emitidos el estado ya informa el consumo del día.
            fresh = client.get("/member/access/code", headers=member_headers).json()
            assert fresh["status"] == "none"
            assert fresh["entries_today"] == 0
            assert fresh["daily_entry_limit"] == 2

            issued = client.post("/member/access/code", headers=member_headers)
            assert issued.status_code == 201, issued.text
            granted = client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": issued.json()["code"]}
            )
            assert granted.status_code == 200, granted.text
            assert granted.json()["authorized"] is True

            # El sondeo que detecta el consumo trae también la entrada recién
            # registrada, que es la que cuenta para el límite del plan.
            after = client.get("/member/access/code", headers=member_headers).json()
            assert after["status"] == "consumed"
            assert after["entries_today"] == 1
            assert after["daily_entry_limit"] == 2

            assert (
                count_member_entries_today(
                    Session(engine), ids["ana"], timezone_name="UTC"
                )
                == 1
            )

            # Un plan sin límite sigue informando el consumo, sin tope.
            with Session(engine) as session:
                plan = session.get(Plan, ids["plan"])
                plan.daily_entry_limit = None
                session.add(plan)
                session.commit()
            unlimited = client.get("/member/access/code", headers=member_headers).json()
            assert unlimited["entries_today"] == 1
            assert unlimited["daily_entry_limit"] is None
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_kiosk_token_expiry_is_announced_to_settings_managers(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        now = utc_now()
        # A full 90-day token issued 80 days ago is ten days from expiring, and
        # one issued 95 days ago already lapsed.
        soon, _ = create_kiosk_device(
            session, label="Recepción", now=now - timedelta(days=80)
        )
        soon_id = soon.id
        create_kiosk_device(
            session, label="Recepción bodega", now=now - timedelta(days=95)
        )
        session.add(
            KioskDevice(label="Sin caducidad", token_sha256="0" * 64, token_expires_at=None)
        )
        session.commit()

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            reception = _login_staff(
                client, "reception@example.com", "reception-strong-password"
            )

            # The bell poll is what materialises the notices: no scheduler.
            assert (
                client.get("/admin/notifications/unread-count", headers=owner).json()[
                    "unread"
                ]
                == 2
            )
            inbox = client.get("/admin/notifications", headers=owner).json()
            assert inbox["total"] == 2
            bodies = {item["body"] for item in inbox["items"]}
            assert all(item["kind"] == "kiosk_token_expiring" for item in inbox["items"])
            assert any(
                "«Recepción»" in body and "faltan 10 días" in body for body in bodies
            )
            assert any("«Recepción bodega»" in body and "caducó el" in body for body in bodies)
            assert not any("Sin caducidad" in body for body in bodies)
            assert {item["ref_id"] for item in inbox["items"]} != {None}

            # Reading again does not duplicate the same alert.
            client.get("/admin/notifications", headers=owner)
            assert client.get("/admin/notifications", headers=owner).json()["total"] == 2

            # Only the accounts that can rotate receive it.
            assert client.get("/admin/notifications", headers=reception).json()["total"] == 0
            assert (
                client.get(
                    "/admin/notifications/unread-count", headers=reception
                ).json()["unread"]
                == 0
            )

            # A rotation moves the expiry date, so the next window alerts again.
            rotated = client.post(
                f"/admin/kiosk/devices/{soon_id}/rotate-token", headers=owner
            )
            assert rotated.status_code == 200, rotated.text
            with Session(engine) as session:
                stored = session.get(KioskDevice, soon_id)
                stored.token_expires_at = utc_now() + timedelta(days=5)
                session.add(stored)
                session.commit()

            assert client.get("/admin/notifications", headers=owner).json()["total"] == 3
            newest = client.get("/admin/notifications", headers=owner).json()["items"]
            assert any(
                item["ref_id"] == str(soon_id) and "faltan 5 días" in item["body"]
                for item in newest
            )
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_kiosk_token_rotation_replaces_the_device_token(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            reception = _login_staff(client, "reception@example.com", "reception-strong-password")
            device = _create_device(client, owner)
            assert device["token_expires_at"] is not None
            issued_expiry = datetime.fromisoformat(device["token_expires_at"])
            if issued_expiry.tzinfo is None:
                issued_expiry = issued_expiry.replace(tzinfo=timezone.utc)
            assert issued_expiry > datetime.now(timezone.utc) + timedelta(days=89)
            old_token = device["token"]
            old_headers = {"X-Kiosk-Token": old_token}
            assert client.get("/kiosk/equipment", headers=old_headers).status_code == 200

            rotate_path = f"/admin/kiosk/devices/{device['id']}/rotate-token"
            assert client.post(rotate_path, headers=reception).status_code == 403
            assert client.post(
                "/admin/kiosk/devices/00000000-0000-0000-0000-000000000000/rotate-token",
                headers=owner,
            ).status_code == 404

            rotated = client.post(rotate_path, headers=owner)
            assert rotated.status_code == 200, rotated.text
            rotated_body = rotated.json()
            new_token = rotated_body["token"]
            assert new_token != old_token
            assert rotated_body["status"] == "active"
            assert rotated_body["token_expires_at"] is not None

            assert client.get("/kiosk/equipment", headers=old_headers).status_code == 401
            assert client.get(
                "/kiosk/equipment", headers={"X-Kiosk-Token": new_token}
            ).status_code == 200

            listed = client.get("/admin/kiosk/devices", headers=owner).json()["items"]
            assert listed[0]["token_expires_at"] == rotated_body["token_expires_at"]
            assert "token" not in listed[0]

            assert client.post(
                f"/admin/kiosk/devices/{device['id']}/revoke", headers=owner
            ).status_code == 200
            assert client.post(rotate_path, headers=owner).status_code == 409
            assert client.get(
                "/kiosk/equipment", headers={"X-Kiosk-Token": new_token}
            ).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_kiosk_token_expires_after_ninety_days(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-kiosk-token-secret")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        base = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
        device, token = create_kiosk_device(session, label="Tablet", now=base)
        # SQLite drops the timezone on the way out; the stored value is UTC.
        assert device.token_expires_at.replace(
            tzinfo=timezone.utc
        ) == base + KIOSK_TOKEN_LIFETIME

        last_valid = base + KIOSK_TOKEN_LIFETIME - timedelta(seconds=1)
        assert authenticate_kiosk_device(session, token, now=last_valid).id == device.id

        try:
            authenticate_kiosk_device(session, token, now=base + KIOSK_TOKEN_LIFETIME)
        except InvalidKioskToken:
            pass
        else:
            raise AssertionError("A token must be rejected once it expires")

        # Devices created before the column existed have no expiry date and keep
        # working until they are rotated or revoked.
        device.token_expires_at = None
        session.add(device)
        session.commit()
        assert (
            authenticate_kiosk_device(session, token, now=base + timedelta(days=400)).id
            == device.id
        )
    engine.dispose()


def test_kiosk_denies_without_current_membership(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            device = _create_device(client, owner)
            kiosk_headers = {"X-Kiosk-Token": device["token"]}

            for email in ("beto@example.com", "carla@example.com"):
                member_headers = _login_member(client, email)
                rejected = client.post("/member/access/code", headers=member_headers)
                assert rejected.status_code == 409
                assert "membresía no está activa" in rejected.json()["detail"]

            ana_headers = _login_member(client, "ana@example.com")
            issued = client.post("/member/access/code", headers=ana_headers)
            assert issued.status_code == 201
            code = issued.json()["code"]

            with Session(engine) as session:
                membership = session.exec(
                    select(Membership).where(Membership.member_id == ids["ana"])
                ).one()
                membership.ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
                session.add(membership)
                session.commit()

            denied = client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": code}
            )
            assert denied.status_code == 200, denied.text
            body = denied.json()
            assert body["authorized"] is False
            assert body["reason"] == "membership_expired"
            assert body["message"] == "Membresía vencida. Pasa a recepción."

            second_try = client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": code}
            )
            assert second_try.status_code == 400

            events = client.get("/admin/access-events", headers=owner).json()
            assert events["total"] == 1
            assert events["items"][0]["authorized"] is False
            assert events["items"][0]["reason"] == "membership_expired"
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_kiosk_rate_limits_codes_and_attempts(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            device = _create_device(client, owner)
            other_device = _create_device(client, owner, label="Recepción 2")
            member_headers = _login_member(client, "ana@example.com")

            code = None
            for _ in range(ACCESS_CODE_MAX_REQUESTS):
                issued = client.post("/member/access/code", headers=member_headers)
                assert issued.status_code == 201, issued.text
                code = issued.json()["code"]

            limited = client.post("/member/access/code", headers=member_headers)
            assert limited.status_code == 429
            assert "Espera unos minutos" in limited.json()["detail"]

            kiosk_headers = {"X-Kiosk-Token": device["token"]}
            for index in range(10):
                wrong = client.post(
                    "/kiosk/check-in",
                    headers=kiosk_headers,
                    json={"code": _wrong_code(code, index)},
                )
                assert wrong.status_code == 400, wrong.text

            blocked = client.post(
                "/kiosk/check-in", headers=kiosk_headers, json={"code": code}
            )
            assert blocked.status_code == 429
            assert "Demasiados intentos" in blocked.json()["detail"]

            with Session(engine) as session:
                attempts = session.exec(select(KioskAttempt)).all()
                assert len(attempts) == 10
                assert {attempt.result for attempt in attempts} == {"invalid"}

            other_headers = {"X-Kiosk-Token": other_device["token"]}
            granted = client.post(
                "/kiosk/check-in", headers=other_headers, json={"code": code}
            )
            assert granted.status_code == 200, granted.text
            assert granted.json()["authorized"] is True
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_access_code_expires_five_minutes_after_issue(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-kiosk-access-secret")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)
        device, _ = create_kiosk_device(session, label="Tablet")
        now = datetime.now(timezone.utc)

        first = issue_member_access_code(session, ids["ana"], now=now)
        granted = check_in_with_code(
            session, device=device, code=first.code, now=now + timedelta(minutes=1)
        )
        assert granted.authorized is True

        second = issue_member_access_code(session, ids["ana"], now=now + timedelta(minutes=2))
        assert second.expires_at == now + timedelta(minutes=7)
        try:
            check_in_with_code(
                session, device=device, code=second.code, now=now + timedelta(minutes=7)
            )
        except InvalidAccessCode:
            pass
        else:
            raise AssertionError("An expired code must be rejected")
    engine.dispose()


def test_plan_daily_entry_limit_blocks_kiosk_and_counts_manual_entries(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("APP_TIMEZONE", "America/Mexico_City")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            reception = _login_staff(client, "reception@example.com", "reception-strong-password")
            device = _create_device(client, owner)
            kiosk_headers = {"X-Kiosk-Token": device["token"]}
            plan_path = f"/admin/plans/{ids['plan']}"

            assert client.patch(
                plan_path, headers=reception, json={"daily_entry_limit": 2}
            ).status_code == 403
            assert client.patch(
                plan_path, headers=owner, json={"daily_entry_limit": 0}
            ).status_code == 422
            assert client.patch(
                "/admin/plans/00000000-0000-0000-0000-000000000000",
                headers=owner,
                json={"daily_entry_limit": 2},
            ).status_code == 404

            limited = client.patch(
                plan_path, headers=owner, json={"daily_entry_limit": 1}
            )
            assert limited.status_code == 200, limited.text
            assert limited.json()["daily_entry_limit"] == 1
            listed = client.get("/admin/plans", headers=owner).json()
            assert listed[0]["daily_entry_limit"] == 1

            manual = client.post(
                "/admin/access-events/manual",
                headers=reception,
                json={"member_id": str(ids["ana"]), "note": "Cortesía"},
            )
            assert manual.status_code == 201, manual.text
            assert manual.json()["authorized"] is True

            member_headers = _login_member(client, "ana@example.com")
            issued = client.post("/member/access/code", headers=member_headers)
            assert issued.status_code == 201, issued.text
            denied = client.post(
                "/kiosk/check-in",
                headers=kiosk_headers,
                json={"code": issued.json()["code"]},
            )
            assert denied.status_code == 200, denied.text
            assert denied.json()["authorized"] is False
            assert denied.json()["reason"] == "daily_limit"
            assert denied.json()["message"] == "Ya usaste tus entradas de hoy."

            cleared = client.patch(
                plan_path, headers=owner, json={"daily_entry_limit": None}
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["daily_entry_limit"] is None

            issued_again = client.post("/member/access/code", headers=member_headers)
            assert issued_again.status_code == 201, issued_again.text
            granted = client.post(
                "/kiosk/check-in",
                headers=kiosk_headers,
                json={"code": issued_again.json()["code"]},
            )
            assert granted.status_code == 200, granted.text
            assert granted.json()["authorized"] is True

            events = client.get("/admin/access-events", headers=owner).json()
            assert events["total"] == 3
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_antipassback_window_blocks_repeated_kiosk_entries(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            reception = _login_staff(client, "reception@example.com", "reception-strong-password")
            device = _create_device(client, owner)
            kiosk_headers = {"X-Kiosk-Token": device["token"]}
            settings_path = "/admin/access/settings"

            assert client.get(settings_path, headers=reception).status_code == 403
            assert client.patch(
                settings_path, headers=reception, json={"antipassback_seconds": 60}
            ).status_code == 403
            assert client.patch(
                settings_path, headers=owner, json={"antipassback_seconds": -1}
            ).status_code == 422
            assert client.patch(
                settings_path, headers=owner, json={"antipassback_seconds": 3601}
            ).status_code == 422

            initial = client.get(settings_path, headers=owner)
            assert initial.status_code == 200, initial.text
            assert initial.json()["antipassback_seconds"] == 0

            enabled = client.patch(
                settings_path, headers=owner, json={"antipassback_seconds": 600}
            )
            assert enabled.status_code == 200, enabled.text
            assert enabled.json()["antipassback_seconds"] == 600

            manual = client.post(
                "/admin/access-events/manual",
                headers=reception,
                json={"member_id": str(ids["ana"]), "note": "Cortesía"},
            )
            assert manual.status_code == 201, manual.text
            assert manual.json()["authorized"] is True

            member_headers = _login_member(client, "ana@example.com")
            issued = client.post("/member/access/code", headers=member_headers)
            assert issued.status_code == 201, issued.text
            denied = client.post(
                "/kiosk/check-in",
                headers=kiosk_headers,
                json={"code": issued.json()["code"]},
            )
            assert denied.status_code == 200, denied.text
            assert denied.json()["authorized"] is False
            assert denied.json()["reason"] == "antipassback"
            assert denied.json()["message"] == "Entrada duplicada. Espera un momento."

            disabled = client.patch(
                settings_path, headers=owner, json={"antipassback_seconds": 0}
            )
            assert disabled.status_code == 200, disabled.text
            assert disabled.json()["antipassback_seconds"] == 0

            issued_again = client.post("/member/access/code", headers=member_headers)
            assert issued_again.status_code == 201, issued_again.text
            granted = client.post(
                "/kiosk/check-in",
                headers=kiosk_headers,
                json={"code": issued_again.json()["code"]},
            )
            assert granted.status_code == 200, granted.text
            assert granted.json()["authorized"] is True

            events = client.get("/admin/access-events", headers=owner).json()
            assert events["total"] == 3
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_last_member_entry_at_includes_manual_entries() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)

        def add_event(
            authorized: bool,
            occurred_at: datetime,
            *,
            direction: AccessDirection = AccessDirection.ENTRY,
            reason: AccessReason = AccessReason.ENTRY_ALLOWED,
            source: str = "reader",
        ) -> None:
            record_access_event(
                session,
                AccessDecision(
                    event_id=uuid4(),
                    member_id=ids["ana"],
                    authorized=authorized,
                    reason=reason,
                    direction=direction,
                    occurred_at=occurred_at,
                    offline=False,
                ),
                reader_id="Prueba",
                source=source,
            )

        base = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
        add_event(True, base)
        add_event(
            False,
            base + timedelta(minutes=1),
            reason=AccessReason.ANTIPASSBACK,
        )
        add_event(
            True,
            base + timedelta(minutes=2),
            direction=AccessDirection.EXIT,
            reason=AccessReason.EXIT_ALLOWED,
        )
        add_event(
            True,
            base + timedelta(minutes=3),
            reason=AccessReason.MANUAL_OVERRIDE,
            source="manual",
        )

        assert last_member_entry_at(session, ids["ana"]) == base + timedelta(minutes=3)
        assert last_member_entry_at(
            session, ids["ana"], before=base + timedelta(minutes=3)
        ) == base
        assert last_member_entry_at(session, ids["beto"]) is None

        assert read_antipassback_seconds(session) == 0
        try:
            update_antipassback_seconds(session, -1)
        except ValueError:
            pass
        else:
            raise AssertionError("A negative window must be rejected")
        assert update_antipassback_seconds(
            session, 120, now=base
        ).antipassback_seconds == 120
        assert read_antipassback_seconds(session) == 120
        assert update_antipassback_seconds(
            session, 0, now=base
        ).antipassback_seconds == 0
    engine.dispose()


def test_count_member_entries_today_uses_the_club_day() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)

        def add_event(
            authorized: bool,
            occurred_at: datetime,
            *,
            direction: AccessDirection = AccessDirection.ENTRY,
            reason: AccessReason = AccessReason.ENTRY_ALLOWED,
        ) -> None:
            record_access_event(
                session,
                AccessDecision(
                    event_id=uuid4(),
                    member_id=ids["ana"],
                    authorized=authorized,
                    reason=reason,
                    direction=direction,
                    occurred_at=occurred_at,
                    offline=False,
                ),
                reader_id="Prueba",
            )

        # Mexico City is UTC-6: the club day starts at 06:00 UTC.
        add_event(True, datetime(2026, 10, 28, 5, 59, tzinfo=timezone.utc))
        add_event(True, datetime(2026, 10, 28, 6, 1, tzinfo=timezone.utc))
        add_event(
            False,
            datetime(2026, 10, 28, 7, 0, tzinfo=timezone.utc),
            reason=AccessReason.DAILY_LIMIT,
        )
        add_event(
            True,
            datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc),
            direction=AccessDirection.EXIT,
            reason=AccessReason.EXIT_ALLOWED,
        )

        noon = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)
        assert count_member_entries_today(
            session, ids["ana"], timezone_name="America/Mexico_City", now=noon
        ) == 1
        next_day = datetime(2026, 10, 29, 7, 0, tzinfo=timezone.utc)
        assert count_member_entries_today(
            session, ids["ana"], timezone_name="America/Mexico_City", now=next_day
        ) == 0
    engine.dispose()


def test_member_row_lock_precedes_the_limits_read(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-kiosk-access-secret")
    monkeypatch.setenv("APP_TIMEZONE", "America/Mexico_City")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    order: list[str] = []
    real_lock = kiosk_module._lock_member_row
    real_count = kiosk_module.count_member_entries_today

    def spy_lock(session: Session, member_id: UUID) -> None:
        order.append("lock")
        real_lock(session, member_id)

    def spy_count(*args, **kwargs):
        order.append("count")
        return real_count(*args, **kwargs)

    monkeypatch.setattr(kiosk_module, "_lock_member_row", spy_lock)
    monkeypatch.setattr(kiosk_module, "count_member_entries_today", spy_count)

    with Session(engine) as session:
        ids = _seed(session)
        plan = session.get(Plan, ids["plan"])
        plan.daily_entry_limit = 3
        session.add(plan)
        device, _ = create_kiosk_device(session, label="Tablet")
        now = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)

        issued = issue_member_access_code(session, ids["ana"], now=now)
        assert order == ["lock"]
        order.clear()

        granted = check_in_with_code(
            session, device=device, code=issued.code, now=now + timedelta(seconds=30)
        )
        assert granted.authorized is True
    assert order == ["lock", "count"]
    engine.dispose()


def test_member_row_lock_is_for_update_on_postgresql() -> None:
    statement = kiosk_module._member_lock_statement(uuid4())
    sql = " ".join(str(statement.compile(dialect=postgresql.dialect())).split())
    assert sql.startswith("SELECT members.id FROM members WHERE members.id = ")
    assert sql.endswith("FOR UPDATE")
    # SQLite drops the clause, which is why the preview cannot prove the
    # serialization: PostgreSQL does the real work in production.
    sqlite_sql = " ".join(
        str(statement.compile(dialect=sqlite.dialect())).split()
    )
    assert "FOR UPDATE" not in sqlite_sql


def test_plan_schedule_windows_are_configured_from_the_panel(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            reception = _login_staff(client, "reception@example.com", "reception-strong-password")
            windows_path = f"/admin/plans/{ids['plan']}/access-windows"
            morning = {"weekday": 0, "starts_at": "06:00", "ends_at": "22:00"}

            assert client.put(
                windows_path, headers=reception, json={"windows": [morning]}
            ).status_code == 403
            assert client.put(
                "/admin/plans/00000000-0000-0000-0000-000000000000/access-windows",
                headers=owner,
                json={"windows": [morning]},
            ).status_code == 404

            invalid_day = client.put(
                windows_path, headers=owner, json={"windows": [{**morning, "weekday": 7}]}
            )
            assert invalid_day.status_code == 422
            empty_span = client.put(
                windows_path,
                headers=owner,
                json={"windows": [{"weekday": 0, "starts_at": "08:00", "ends_at": "08:00"}]},
            )
            assert empty_span.status_code == 422
            assert "no pueden ser iguales" in empty_span.json()["detail"]
            duplicated = client.put(
                windows_path, headers=owner, json={"windows": [morning, morning]}
            )
            assert duplicated.status_code == 422
            assert "mismo día y las mismas horas" in duplicated.json()["detail"]
            overlapping = client.put(
                windows_path,
                headers=owner,
                json={
                    "windows": [
                        {"weekday": 0, "starts_at": "06:00", "ends_at": "12:00"},
                        {"weekday": 0, "starts_at": "11:00", "ends_at": "15:00"},
                    ]
                },
            )
            assert overlapping.status_code == 422
            assert "traslapan" in overlapping.json()["detail"]
            overnight_tail = client.put(
                windows_path,
                headers=owner,
                json={
                    "windows": [
                        {"weekday": 0, "starts_at": "22:00", "ends_at": "02:00"},
                        {"weekday": 1, "starts_at": "01:00", "ends_at": "06:00"},
                    ]
                },
            )
            assert overnight_tail.status_code == 422

            saved = client.put(
                windows_path,
                headers=owner,
                json={
                    "windows": [
                        {"weekday": 0, "starts_at": "06:00", "ends_at": "22:00"},
                        {"weekday": 6, "starts_at": "08:00", "ends_at": "14:00"},
                    ]
                },
            )
            assert saved.status_code == 200, saved.text
            assert saved.json()["access_windows"] == [
                {"weekday": 0, "starts_at": "06:00:00", "ends_at": "22:00:00"},
                {"weekday": 6, "starts_at": "08:00:00", "ends_at": "14:00:00"},
            ]
            listed = client.get("/admin/plans", headers=owner).json()
            assert listed[0]["access_windows"] == saved.json()["access_windows"]

            cleared = client.put(windows_path, headers=owner, json={"windows": []})
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["access_windows"] == []
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_kiosk_denies_outside_the_plan_schedule(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-kiosk-access-secret")
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ids = _seed(session)
        device, _ = create_kiosk_device(session, label="Tablet")
        monday_morning = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)
        monday_night = datetime(2026, 10, 26, 23, 0, tzinfo=timezone.utc)
        tuesday_early = datetime(2026, 10, 27, 1, 0, tzinfo=timezone.utc)
        tuesday_after = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)

        replace_plan_access_windows(
            session,
            ids["plan"],
            [AccessWindow(weekday=0, starts_at=time(6, 0), ends_at=time(22, 0))],
        )
        granted = check_in_with_code(
            session,
            device=device,
            code=issue_member_access_code(session, ids["ana"], now=monday_morning).code,
            now=monday_morning,
        )
        assert granted.authorized is True

        denied = check_in_with_code(
            session,
            device=device,
            code=issue_member_access_code(session, ids["ana"], now=monday_night).code,
            now=monday_night,
        )
        assert denied.authorized is False
        assert denied.reason == "outside_allowed_hours"
        assert denied.message == "Estás fuera del horario permitido."

        # A window that ends before it starts covers the next morning.
        replace_plan_access_windows(
            session,
            ids["plan"],
            [AccessWindow(weekday=0, starts_at=time(22, 0), ends_at=time(2, 0))],
        )
        overnight = check_in_with_code(
            session,
            device=device,
            code=issue_member_access_code(session, ids["ana"], now=tuesday_early).code,
            now=tuesday_early,
        )
        assert overnight.authorized is True
        late = check_in_with_code(
            session,
            device=device,
            code=issue_member_access_code(session, ids["ana"], now=tuesday_after).code,
            now=tuesday_after,
        )
        assert late.authorized is False
        assert late.reason == "outside_allowed_hours"

        # Without windows the plan is open again at any hour.
        replace_plan_access_windows(session, ids["plan"], [])
        reopened = check_in_with_code(
            session,
            device=device,
            code=issue_member_access_code(session, ids["ana"], now=tuesday_after).code,
            now=tuesday_after,
        )
        assert reopened.authorized is True
    engine.dispose()
