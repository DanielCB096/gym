"""The member finds out when their invoice changes state.

Stamping, a PAC rejection and a cancellation all reach the member's in-app
inbox, once per invoice and status, with ``ref_id`` pointing at the invoice so
the app can open Facturas. Invoices without a member -- walk-in sales and the
global public invoice -- have nobody to notify.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.billing import service as billing_service
from app.modules.billing.errors import PacRejected
from app.modules.billing.pac import SimulatedPac
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import Product, Sale, SaleItem
from app.modules.memberships.models import (
    Member,
    Membership,
    Payment,
    PaymentAttempt,
    Plan,
)
from app.modules.notifications import MemberNotification, list_member_notifications


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


def _seed_member(session: Session, *, email: str, first_name: str) -> tuple[UUID, UUID]:
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
        # Outside every expiry reminder window so those notices never mix in.
        ends_at=now + timedelta(days=60),
    )
    session.add(membership)
    session.flush()
    attempt = PaymentAttempt(
        membership_id=membership.id,
        method="cash",
        idempotency_key=f"attempt-{uuid4()}",
        request_fingerprint="f" * 64,
        attempt_number=1,
        amount_cents=50000,
        status="succeeded",
        due_at=now,
    )
    session.add(attempt)
    session.flush()
    payment = Payment(
        payment_attempt_id=attempt.id,
        member_id=member.id,
        membership_id=membership.id,
        amount_cents=50000,
        currency="MXN",
        method="cash",
        paid_at=now,
        period_starts_at=now,
        period_ends_at=now + timedelta(days=30),
    )
    session.add(payment)
    session.commit()
    return member.id, payment.id


def _seed_sale(session: Session, *, member_id: UUID | None, total_cents: int = 11600) -> UUID:
    product = Product(
        sku=f"SKU-{uuid4().hex[:8].upper()}", name="Proteína", price_cents=total_cents
    )
    session.add(product)
    session.flush()
    sale = Sale(
        folio=f"V-{uuid4().hex[:8].upper()}",
        member_id=member_id,
        subtotal_cents=total_cents,
        total_cents=total_cents,
        payment_method="cash",
        status="completed",
        sold_at=datetime.now(timezone.utc),
    )
    session.add(sale)
    session.flush()
    session.add(
        SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            product_name="Proteína",
            sku=product.sku,
            quantity=1,
            unit_price_cents=total_cents,
            line_total_cents=total_cents,
            location="Mostrador",
        )
    )
    session.commit()
    return sale.id


def _prepare():
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="accountant@example.com",
            password="accountant-strong-password",
            role_codes=("accountant",),
        )
        ana_id, _ = _seed_member(session, email="ana@example.com", first_name="Ana")
        beto_id, _ = _seed_member(session, email="beto@example.com", first_name="Beto")
        ids = {
            "ana": ana_id,
            "beto": beto_id,
            "ana_sale": _seed_sale(session, member_id=ana_id),
            "beto_sale": _seed_sale(session, member_id=beto_id),
            "walk_in": _seed_sale(session, member_id=None),
        }
    return engine, ids


def _override(engine):
    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return override_session


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _create_invoice(
    client: TestClient,
    headers: dict[str, str],
    sale_id: UUID,
    key: str,
) -> str:
    response = client.post(
        "/admin/billing/invoices",
        headers=headers,
        json={
            "origin_type": "sale",
            "origin_id": str(sale_id),
            "idempotency_key": key,
            "receptor": {
                "rfc": "LOPA800101AAA",
                "legal_name": "Ana López",
                "tax_regime": "612",
                "postal_code": "06700",
                "cfdi_use": "G03",
                "email": "ana.lopez@correo.com.mx",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["invoice"]["id"]


def _kinds(session: Session, member_id: UUID) -> list[str]:
    return [
        row.kind
        for row in list_member_notifications(session, member_id=member_id, page_size=50).items
    ]


def test_invoice_lifecycle_reaches_the_owner_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-invoice-notice-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("PAC_PROVIDER", "simulated")

    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            accountant = _login(
                client, "accountant@example.com", "accountant-strong-password"
            )
            ana = _member_headers(client, "ana@example.com")
            beto = _member_headers(client, "beto@example.com")

            invoice_id = _create_invoice(client, accountant, ids["ana_sale"], "ana-sale")

            # Requesting is the requester's own action: it does not notify.
            assert client.get("/member/notifications", headers=ana).json()["total"] == 0

            stamped = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert stamped.status_code == 200, stamped.text

            inbox = client.get("/member/notifications", headers=ana).json()
            assert inbox["total"] == 1
            assert inbox["unread_total"] == 1
            notice = inbox["items"][0]
            assert notice["kind"] == "invoice_stamped"
            assert notice["title"] == "Factura timbrada"
            assert "A-000001" in notice["body"]
            assert "$116.00 MXN" in notice["body"]
            assert "sin validez fiscal" in notice["body"]
            assert notice["ref_id"] == invoice_id

            # Stamping an already stamped invoice is a no-op for the inbox too.
            replay = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert replay.status_code == 200, replay.text
            assert len(_kinds(Session(engine), ids["ana"])) == 1

            cancelled = client.post(
                f"/admin/billing/invoices/{invoice_id}/cancel",
                headers=accountant,
                json={"reason_code": "02"},
            )
            assert cancelled.status_code == 200, cancelled.text

            inbox = client.get("/member/notifications", headers=ana).json()
            assert inbox["total"] == 2
            newest = inbox["items"][0]
            assert newest["kind"] == "invoice_cancelled"
            assert newest["title"] == "Factura cancelada"
            assert "A-000001" in newest["body"]
            assert newest["ref_id"] == invoice_id

            # The notice is private: Beto sees nothing.
            assert client.get("/member/notifications", headers=beto).json()["total"] == 0

            # A walk-in sale has no member: its invoice is stamped silently.
            walk_in_id = _create_invoice(client, accountant, ids["walk_in"], "walk-in")
            walk_in_stamp = client.post(
                f"/admin/billing/invoices/{walk_in_id}/stamp", headers=accountant
            )
            assert walk_in_stamp.status_code == 200, walk_in_stamp.text
            with Session(engine) as session:
                assert [row.kind for row in session.exec(
                    select(MemberNotification).where(
                        MemberNotification.ref_id == UUID(walk_in_id)
                    )
                ).all()] == []
                assert _kinds(session, ids["ana"]) == [
                    "invoice_cancelled",
                    "invoice_stamped",
                ]
                assert _kinds(session, ids["beto"]) == []
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_rejection_notifies_failure_once_and_recovery_notifies_stamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-invoice-notice-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("PAC_PROVIDER", "simulated")

    class FlakyPac:
        reject = True

        def stamp(self, xml: str):
            if self.reject:
                raise PacRejected("El PAC rechazó el comprobante.", code="test_rejected")
            return SimulatedPac().stamp(xml)

        def cancel(self, *, uuid, reason_code, replacement_uuid):
            return SimulatedPac().cancel(
                uuid=uuid,
                reason_code=reason_code,
                replacement_uuid=replacement_uuid,
            )

    pac = FlakyPac()
    monkeypatch.setattr(billing_service, "pac_gateway", lambda: pac)

    engine, ids = _prepare()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            accountant = _login(
                client, "accountant@example.com", "accountant-strong-password"
            )
            beto = _member_headers(client, "beto@example.com")
            invoice_id = _create_invoice(
                client, accountant, ids["beto_sale"], "beto-sale"
            )

            rejected = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert rejected.status_code == 502, rejected.text

            inbox = client.get("/member/notifications", headers=beto).json()
            assert inbox["total"] == 1
            notice = inbox["items"][0]
            assert notice["kind"] == "invoice_failed"
            assert notice["title"] == "No pudimos timbrar tu factura"
            assert "A-000001" in notice["body"]
            assert "$116.00 MXN" in notice["body"]
            assert "datos fiscales" in notice["body"]
            assert notice["ref_id"] == invoice_id

            # A second failed attempt is the same fact: no duplicate.
            rejected_again = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert rejected_again.status_code == 502, rejected_again.text
            assert len(_kinds(Session(engine), ids["beto"])) == 1

            # Retrying after the PAC recovers stamps it and tells the member.
            pac.reject = False
            recovered = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert recovered.status_code == 200, recovered.text

            with Session(engine) as session:
                assert _kinds(session, ids["beto"]) == [
                    "invoice_stamped",
                    "invoice_failed",
                ]
    finally:
        app.dependency_overrides.pop(get_session, None)
