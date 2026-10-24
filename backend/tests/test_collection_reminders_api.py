from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory import statements
from app.modules.inventory.models import (
    MemberAccountStatementDelivery,
    Sale,
    utc_now,
)
from app.modules.memberships.models import Member


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


def _seed_users(session: Session) -> None:
    ensure_default_access_control(session)
    for email, password, role in (
        ("manager@example.com", "manager-strong-password", "manager"),
        ("reception@example.com", "reception-strong-password", "reception"),
        ("accountant@example.com", "accountant-strong-password", "accountant"),
        ("trainer@example.com", "trainer-strong-password", "trainer"),
    ):
        register_user(session, email=email, password=password, role_codes=(role,))


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _seed_members(session: Session) -> tuple[UUID, UUID, UUID]:
    ana = Member(
        first_name="Ana",
        last_name="Lopez",
        email="ana@example.com",
        phone="+52 555 123 4567",
        status="active",
    )
    no_email = Member(first_name="Beto", last_name="Ruiz", status="active")
    carla = Member(
        first_name="Carla",
        last_name="Mendez",
        email="carla@example.com",
        status="active",
    )
    session.add_all([ana, no_email, carla])
    session.commit()
    return ana.id, no_email.id, carla.id


def _create_product(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/admin/products",
        headers=headers,
        json={
            "sku": "agua-600",
            "name": "Agua 600 ml",
            "category": "Bebidas",
            "price_cents": 1500,
            "initial_stock": 40,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _charge_account(
    client: TestClient,
    headers: dict[str, str],
    product_id: str,
    member_id: UUID,
    quantity: int = 2,
) -> dict:
    response = client.post(
        "/admin/sales",
        headers=headers,
        json={
            "items": [{"product_id": product_id, "quantity": quantity}],
            "payment_method": "account",
            "member_id": str(member_id),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _age_sale(engine, sale_id: str, days: int = 45) -> None:
    with Session(engine) as session:
        sale = session.get(Sale, UUID(sale_id))
        assert sale is not None
        sale.sold_at = utc_now() - timedelta(days=days)
        session.add(sale)
        session.commit()


def _prepare_overdue_accounts(
    client: TestClient,
    manager: dict[str, str],
    reception: dict[str, str],
    engine,
    member_ids: tuple[UUID, UUID, UUID],
) -> dict[UUID, dict]:
    product_id = _create_product(client, manager)
    client.post(
        "/admin/cash-sessions",
        headers=reception,
        json={"opening_cash_cents": 0},
    )
    ana_id, beto_id, carla_id = member_ids
    ana_sale = _charge_account(client, reception, product_id, ana_id)
    beto_sale = _charge_account(client, reception, product_id, beto_id)
    _charge_account(client, reception, product_id, carla_id)
    # Ana and Beto carry debt older than 30 days; Carla's charge is current.
    _age_sale(engine, ana_sale["id"], days=45)
    _age_sale(engine, beto_sale["id"], days=61)
    return {"ana": ana_sale, "beto": beto_sale}


def _delivery_rows(engine) -> list[MemberAccountStatementDelivery]:
    with Session(engine) as session:
        return list(
            session.exec(
                select(MemberAccountStatementDelivery).order_by(
                    MemberAccountStatementDelivery.created_at
                )
            ).all()
        )


def test_reminder_batch_permissions_and_request_validation() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_ids = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            _prepare_overdue_accounts(client, manager, reception, engine, member_ids)

            payload = {"member_ids": [str(member_ids[0])], "format": "pdf"}
            assert client.post(
                "/admin/member-accounts/reminders", headers=accountant, json=payload
            ).status_code == 403
            assert client.post(
                "/admin/member-accounts/reminders", headers=trainer, json=payload
            ).status_code == 403
            assert client.post(
                "/admin/member-accounts/reminders", headers=reception, json={}
            ).status_code == 422
            assert client.post(
                "/admin/member-accounts/reminders",
                headers=reception,
                json={"member_ids": []},
            ).status_code == 422
            assert client.post(
                "/admin/member-accounts/reminders",
                headers=reception,
                json={"member_ids": [str(uuid4()) for _ in range(51)]},
            ).status_code == 422

            # Unknown members are reported as skipped, not as a failed batch.
            unknown = client.post(
                "/admin/member-accounts/reminders",
                headers=reception,
                json={"member_ids": [str(uuid4())]},
            )
            assert unknown.status_code == 200, unknown.text
            assert unknown.json()["skipped"] == 1
            assert unknown.json()["results"][0]["reason"] == "Socio no encontrado."
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_reminders_send_only_overdue_accounts_and_respect_cooldown(monkeypatch) -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_ids = _seed_members(session)

    monkeypatch.setenv("PREVIEW_MODE", "true")
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            _prepare_overdue_accounts(client, manager, reception, engine, member_ids)

            response = client.post(
                "/admin/member-accounts/reminders",
                headers=reception,
                json={
                    "member_ids": [str(member_id) for member_id in member_ids],
                    "format": "csv",
                },
            )
            assert response.status_code == 200, response.text
            batch = response.json()
            assert batch["requested"] == 3
            assert batch["sent"] == 0
            assert batch["simulated"] == 1
            assert batch["skipped"] == 2
            assert batch["failed"] == 0

            by_member = {result["member_id"]: result for result in batch["results"]}
            ana_result = by_member[str(member_ids[0])]
            assert ana_result["status"] == "simulated"
            assert ana_result["balance_cents"] == 3000
            assert ana_result["overdue_cents"] == 3000
            assert ana_result["delivery"]["recipient"] == "ana@example.com"
            assert ana_result["delivery"]["format"] == "csv"
            assert ana_result["delivery"]["purpose"] == "reminder"
            assert by_member[str(member_ids[1])]["status"] == "skipped"
            assert "correo" in by_member[str(member_ids[1])]["reason"].lower()
            assert by_member[str(member_ids[2])]["status"] == "skipped"
            assert "30 días" in by_member[str(member_ids[2])]["reason"]

            rows = _delivery_rows(engine)
            assert len(rows) == 1
            assert rows[0].purpose == "reminder"
            assert rows[0].status == "simulated"

            history = client.get(
                f"/admin/member-accounts/{member_ids[0]}/statement/deliveries",
                headers=reception,
            )
            assert history.status_code == 200, history.text
            assert history.json()["items"][0]["purpose"] == "reminder"

            repeated = client.post(
                "/admin/member-accounts/reminders",
                headers=reception,
                json={"member_ids": [str(member_ids[0])]},
            )
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()["skipped"] == 1
            assert "7 días" in repeated.json()["results"][0]["reason"]
            assert len(_delivery_rows(engine)) == 1
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_reminder_retry_keeps_purpose_and_is_blocked_after_payment(monkeypatch) -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_ids = _seed_members(session)

    monkeypatch.setenv("PREVIEW_MODE", "true")
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            _prepare_overdue_accounts(client, manager, reception, engine, member_ids)

            sent = client.post(
                "/admin/member-accounts/reminders",
                headers=reception,
                json={"member_ids": [str(member_ids[0])]},
            )
            assert sent.status_code == 200, sent.text
            original = sent.json()["results"][0]["delivery"]
            assert original["purpose"] == "reminder"
            assert original["status"] == "simulated"

            retry = client.post(
                f"/admin/member-accounts/{member_ids[0]}/statement/deliveries/{original['id']}/retry",
                headers=reception,
            )
            assert retry.status_code == 201, retry.text
            retried = retry.json()
            assert retried["purpose"] == "reminder"
            assert retried["retry_of_id"] == original["id"]
            assert retried["status"] == "simulated"

            account = client.get(
                f"/admin/member-accounts/{member_ids[0]}", headers=reception
            )
            balance = account.json()["summary"]["balance_cents"]
            payment = client.post(
                f"/admin/member-accounts/{member_ids[0]}/payments",
                headers=reception,
                json={"amount_cents": balance, "method": "cash"},
            )
            assert payment.status_code == 201, payment.text
            assert payment.json()["balance_cents"] == 0

            blocked = client.post(
                f"/admin/member-accounts/{member_ids[0]}/statement/deliveries/{retried['id']}/retry",
                headers=reception,
            )
            assert blocked.status_code == 409, blocked.text
            assert "saldo pendiente" in blocked.json()["detail"].lower()
            assert len(_delivery_rows(engine)) == 2
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_reminder_batch_continues_after_one_transport_failure(monkeypatch) -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_ids = _seed_members(session)

    calls: list[str] = []

    def failing_transport(**kwargs):
        calls.append(kwargs["recipient"])
        if kwargs["recipient"] == "ana@example.com":
            raise statements.StatementDeliveryFailed("fallo de transporte simulado")
        return "simulated"

    monkeypatch.setattr(statements, "_send_email", failing_transport)
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            _prepare_overdue_accounts(client, manager, reception, engine, member_ids)
            with Session(engine) as session:
                beto = session.get(Member, member_ids[1])
                assert beto is not None
                beto.email = "beto@example.com"
                session.add(beto)
                session.commit()

            response = client.post(
                "/admin/member-accounts/reminders",
                headers=reception,
                json={"member_ids": [str(member_ids[0]), str(member_ids[1])]},
            )
            assert response.status_code == 200, response.text
            batch = response.json()
            assert batch["failed"] == 1
            assert batch["simulated"] == 1
            by_member = {result["member_id"]: result for result in batch["results"]}
            assert by_member[str(member_ids[0])]["status"] == "failed"
            assert "fallo de transporte" in by_member[str(member_ids[0])]["reason"]
            assert by_member[str(member_ids[1])]["status"] == "simulated"
            assert calls == ["ana@example.com", "beto@example.com"]

            rows = _delivery_rows(engine)
            assert len(rows) == 2
            failed_row = next(row for row in rows if row.member_id == member_ids[0])
            assert failed_row.status == "failed"
            assert failed_row.purpose == "reminder"
            assert failed_row.error and "fallo de transporte" in failed_row.error

            # A failed reminder does not start the seven-day cooldown.
            monkeypatch.setattr(
                statements, "_send_email", lambda **_: "simulated"
            )
            retry_batch = client.post(
                "/admin/member-accounts/reminders",
                headers=reception,
                json={"member_ids": [str(member_ids[0])]},
            )
            assert retry_batch.status_code == 200, retry_batch.text
            assert retry_batch.json()["simulated"] == 1
            assert retry_batch.json()["skipped"] == 0
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
