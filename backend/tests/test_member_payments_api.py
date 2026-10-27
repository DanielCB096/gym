from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import MemberAccountPayment, Sale
from app.modules.memberships.models import (
    Member,
    Membership,
    Payment,
    PaymentAttempt,
    Plan,
)
from app.modules.portal.payments import get_member_account, list_member_payments
from app.modules.portal.service import MemberPortalError


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


def _seed_member(session: Session, *, email: str, first_name: str = "Ana"):
    now = datetime.now(timezone.utc)
    member = Member(first_name=first_name, last_name="Demo", email=email, status="active")
    session.add(member)
    session.flush()
    plan = Plan(
        code=f"PLAN-{uuid4().hex[:8].upper()}",
        name="Mensual",
        duration_days=30,
        price_cents=50000,
    )
    session.add(plan)
    session.flush()
    membership = Membership(
        member_id=member.id,
        plan_id=plan.id,
        status="active",
        starts_at=now - timedelta(days=5),
        ends_at=now + timedelta(days=25),
    )
    session.add(membership)
    session.commit()
    return member.id, membership.id, plan.id


def _seed_payment(
    session: Session,
    *,
    member_id,
    membership_id,
    amount_cents: int,
    method: str,
    paid_at: datetime,
    note: str | None = None,
):
    attempt = PaymentAttempt(
        membership_id=membership_id,
        method=method,
        idempotency_key=f"pay-{uuid4().hex}",
        request_fingerprint=uuid4().hex,
        attempt_number=1,
        amount_cents=amount_cents,
        status="succeeded",
        due_at=paid_at,
    )
    session.add(attempt)
    session.flush()
    payment = Payment(
        payment_attempt_id=attempt.id,
        member_id=member_id,
        membership_id=membership_id,
        amount_cents=amount_cents,
        currency="MXN",
        method=method,
        paid_at=paid_at,
        period_starts_at=paid_at,
        period_ends_at=paid_at + timedelta(days=30),
        note=note,
    )
    session.add(payment)
    session.commit()
    return payment.id


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_member_payments_and_account(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        ana_id, ana_membership, _ = _seed_member(session, email="ana@example.com")
        beto_id, beto_membership, _ = _seed_member(
            session, email="beto@example.com", first_name="Beto"
        )
        _seed_payment(
            session,
            member_id=ana_id,
            membership_id=ana_membership,
            amount_cents=50000,
            method="cash",
            paid_at=now - timedelta(days=40),
        )
        newest = _seed_payment(
            session,
            member_id=ana_id,
            membership_id=ana_membership,
            amount_cents=55000,
            method="transfer",
            paid_at=now - timedelta(days=3),
            note="Renovación mensual",
        )
        _seed_payment(
            session,
            member_id=beto_id,
            membership_id=beto_membership,
            amount_cents=50000,
            method="cash",
            paid_at=now - timedelta(days=2),
        )
        session.add(
            Sale(
                folio=f"S-{uuid4().hex[:6].upper()}",
                member_id=ana_id,
                subtotal_cents=15000,
                total_cents=15000,
                payment_method="account",
                sold_at=now - timedelta(days=10),
            )
        )
        session.add(
            MemberAccountPayment(
                member_id=ana_id,
                method="cash",
                amount_cents=5000,
                note="Abono en recepción",
                paid_at=now - timedelta(days=1),
            )
        )
        session.commit()

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana_headers = _member_headers(client, "ana@example.com")
            beto_headers = _member_headers(client, "beto@example.com")

            history = client.get("/member/payments", headers=ana_headers)
            assert history.status_code == 200, history.text
            body = history.json()
            assert body["total"] == 2
            assert body["total_paid_cents"] == 105000
            assert body["items"][0]["id"] == str(newest)
            assert body["items"][0]["amount_cents"] == 55000
            assert body["items"][0]["method"] == "transfer"
            assert body["items"][0]["plan_name"] == "Mensual"
            assert body["items"][0]["note"] == "Renovación mensual"
            assert body["items"][0]["period_starts_at"] is not None
            assert "cash_session_id" not in body["items"][0]
            assert "collected_by" not in body["items"][0]
            assert "payment_attempt_id" not in body["items"][0]

            page = client.get(
                "/member/payments?page=2&page_size=1", headers=ana_headers
            )
            assert page.status_code == 200, page.text
            assert page.json()["total"] == 2
            assert page.json()["pages"] == 2
            assert len(page.json()["items"]) == 1
            assert page.json()["items"][0]["method"] == "cash"

            account = client.get("/member/account", headers=ana_headers)
            assert account.status_code == 200, account.text
            data = account.json()
            assert data["charges_cents"] == 15000
            assert data["credits_cents"] == 0
            assert data["payments_cents"] == 5000
            assert data["balance_cents"] == 10000
            assert data["charges_count"] == 1
            assert data["payments_count"] == 1
            assert data["entries_total"] == 2
            assert [entry["kind"] for entry in data["entries"]] == ["payment", "charge"]
            assert data["entries"][0]["balance_cents"] == 10000
            assert data["entries"][1]["balance_cents"] == 15000
            assert data["entries"][0]["description"] == "Pago de cuenta"
            assert "member_id" not in data
            assert "credit_limit_cents" not in data

            beto_history = client.get("/member/payments", headers=beto_headers).json()
            assert beto_history["total"] == 1
            assert beto_history["total_paid_cents"] == 50000
            beto_account = client.get("/member/account", headers=beto_headers).json()
            assert beto_account["balance_cents"] == 0
            assert beto_account["entries"] == []

            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
            assert client.get("/member/payments", headers=staff_headers).status_code == 401
            assert client.get("/member/account", headers=staff_headers).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_member_payments_empty_and_unknown_member(session: Session) -> None:
    ana_id, _, _ = _seed_member(session, email="ana@example.com")

    history = list_member_payments(session, ana_id)
    assert history.total == 0
    assert history.items == []
    assert history.total_paid_cents == 0
    assert history.pages == 0

    clamped = list_member_payments(session, ana_id, page=0, page_size=500)
    assert clamped.page == 1
    assert clamped.page_size == 50

    account = get_member_account(session, ana_id)
    assert account.charges_cents == 0
    assert account.payments_cents == 0
    assert account.balance_cents == 0
    assert account.entries == []
    assert account.entries_total == 0

    unknown = uuid4()
    with pytest.raises(MemberPortalError):
        list_member_payments(session, unknown)
    with pytest.raises(MemberPortalError):
        get_member_account(session, unknown)
