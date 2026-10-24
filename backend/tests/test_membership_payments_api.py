from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, func
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Payment, PaymentAttempt, Plan


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


def _seed_members(session: Session) -> tuple[UUID, UUID, UUID]:
    monthly = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=50000)
    annual = Plan(code="ANNUAL", name="Anual", duration_days=365, price_cents=500000)
    session.add_all([monthly, annual])
    session.flush()

    new_member = Member(first_name="Ana", last_name="Nueva", email="ana@example.test", status="pending")
    frozen_member = Member(first_name="Frida", last_name="Frozen", email="frida@example.test", status="active")
    session.add_all([new_member, frozen_member])
    session.flush()
    now = datetime.now(timezone.utc)
    session.add(
        Membership(
            member_id=frozen_member.id,
            plan_id=monthly.id,
            status="frozen",
            starts_at=now - timedelta(days=10),
            ends_at=now + timedelta(days=20),
        )
    )
    session.commit()
    return new_member.id, frozen_member.id, monthly.id


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _override(engine):
    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return override_session


def test_manual_membership_payment_cash_card_and_close() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _, plan_id = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            opened = client.post(
                "/admin/cash-sessions",
                headers=reception,
                json={"opening_cash_cents": 10000},
            )
            assert opened.status_code == 201, opened.text
            session_id = opened.json()["id"]

            first = client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=reception,
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-first-1",
                    "note": "Primer cobro",
                    "auto_renew": True,
                },
            )
            assert first.status_code == 200, first.text
            first_body = first.json()
            assert first_body["amount_cents"] == 50000
            assert first_body["method"] == "cash"
            assert first_body["renewed"] is False
            assert first_body["membership_status"] == "active"
            assert first_body["cash_session_id"] == session_id
            assert first_body["period_ends_at"] > first_body["period_starts_at"]
            assert first_body["idempotent_replay"] is False

            replay = client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=reception,
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-first-1",
                    "note": "Primer cobro",
                    "auto_renew": True,
                },
            )
            assert replay.status_code == 200, replay.text
            replay_body = replay.json()
            assert replay_body["payment_id"] == first_body["payment_id"]
            assert replay_body["idempotent_replay"] is True

            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["membership_payments_count"] == 1
            assert current["membership_payments_cents"] == 50000
            assert current["cash_membership_payments_cents"] == 50000
            assert current["expected_cash_cents"] == 60000

            member = client.get("/admin/members", headers=reception, params={"search": "ana"}).json()["items"][0]
            assert member["status"] == "active"
            assert member["membership_status"] == "active"
            assert member["plan_name"] == "Mensual"
            assert member["auto_renew"] is True

            renewal = client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=reception,
                json={
                    "payment_method": "card",
                    "idempotency_key": "manual-membership-renewal-1",
                    "note": "Renovación con tarjeta",
                },
            )
            assert renewal.status_code == 200, renewal.text
            renewal_body = renewal.json()
            assert renewal_body["renewed"] is True
            assert renewal_body["period_starts_at"] == first_body["period_ends_at"]
            assert renewal_body["period_ends_at"] > renewal_body["period_starts_at"]
            assert renewal_body["method"] == "card"

            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["membership_payments_count"] == 2
            assert current["membership_payments_cents"] == 100000
            assert current["cash_membership_payments_cents"] == 50000
            assert current["expected_cash_cents"] == 60000

            closed = client.post(
                f"/admin/cash-sessions/{session_id}/close",
                headers=reception,
                json={"counted_cash_cents": 60000},
            )
            assert closed.status_code == 200, closed.text
            closed_body = closed.json()
            assert closed_body["expected_cash_cents"] == 60000
            assert closed_body["difference_cents"] == 0
            assert closed_body["membership_payments_cents"] == 100000
            assert closed_body["cash_membership_payments_cents"] == 50000

        with Session(engine) as session:
            assert session.exec(select(func.count(Payment.id))).one() == 2
            assert session.exec(select(func.count(PaymentAttempt.id))).one() == 2
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_membership_payment_validation_permissions_and_frozen_state() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, frozen_member_id, plan_id = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")

            assert client.post(
                f"/admin/members/{member_id}/membership/payments",
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-no-session",
                },
            ).status_code == 401

            assert client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=accountant,
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-accountant",
                },
            ).status_code == 403
            assert client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=trainer,
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-trainer",
                },
            ).status_code == 403

            no_session = client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=reception,
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-no-session",
                },
            )
            assert no_session.status_code == 409
            assert "turno de caja" in no_session.json()["detail"]

            opened = client.post(
                "/admin/cash-sessions",
                headers=reception,
                json={"opening_cash_cents": 0},
            )
            assert opened.status_code == 201, opened.text

            invalid_method = client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=reception,
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "spei",
                    "idempotency_key": "manual-membership-invalid-method",
                },
            )
            assert invalid_method.status_code == 422

            missing_plan = client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=reception,
                json={
                    "plan_id": str(uuid4()),
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-missing-plan",
                },
            )
            assert missing_plan.status_code == 404

            frozen = client.post(
                f"/admin/members/{frozen_member_id}/membership/payments",
                headers=reception,
                json={
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-frozen",
                },
            )
            assert frozen.status_code == 409

            paid = client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=reception,
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "cash",
                    "idempotency_key": "manual-membership-conflict",
                },
            )
            assert paid.status_code == 200, paid.text

            conflict = client.post(
                f"/admin/members/{member_id}/membership/payments",
                headers=reception,
                json={
                    "plan_id": str(plan_id),
                    "payment_method": "transfer",
                    "idempotency_key": "manual-membership-conflict",
                },
            )
            assert conflict.status_code == 409

        with Session(engine) as session:
            assert session.exec(select(func.count(Payment.id))).one() == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
