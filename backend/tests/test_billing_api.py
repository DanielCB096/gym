from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import mailer
from app.main import app, get_session
from app.modules.billing import service as billing_service
from app.modules.billing.models import Invoice
from app.modules.billing.pac import CancellationOutcome, SatStatusOutcome
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import Product, Sale, SaleItem, SaleReturn
from app.modules.notifications.models import MemberNotification
from app.modules.memberships.models import (
    Member,
    Membership,
    Payment,
    PaymentAttempt,
    Plan,
)
from app.timezone import club_date


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
        ("owner@example.com", "owner-strong-password", "owner"),
        ("manager@example.com", "manager-strong-password", "manager"),
        ("accountant@example.com", "accountant-strong-password", "accountant"),
        ("reception@example.com", "reception-strong-password", "reception"),
        ("trainer@example.com", "trainer-strong-password", "trainer"),
    ):
        register_user(session, email=email, password=password, role_codes=(role,))


def _seed_member_and_payment(session: Session) -> tuple[UUID, UUID, UUID]:
    member = Member(first_name="Ana", last_name="López", email="ana@example.test", status="active")
    plan = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=50000)
    session.add_all([member, plan])
    session.flush()
    now = datetime.now(timezone.utc)
    membership = Membership(
        member_id=member.id,
        plan_id=plan.id,
        status="active",
        starts_at=now,
        ends_at=now + timedelta(days=30),
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
    return member.id, plan.id, payment.id


def _seed_product(session: Session) -> UUID:
    product = Product(sku="PROT-1", name="Proteína", price_cents=11600)
    session.add(product)
    session.commit()
    return product.id


def _seed_sale(
    session: Session,
    *,
    member_id: UUID | None,
    product_id: UUID,
    total_cents: int = 11600,
    payment_method: str = "cash",
    status: str = "completed",
    sold_at: datetime | None = None,
) -> UUID:
    sale = Sale(
        folio=f"V-20261023-{uuid4().hex[:6].upper()}",
        member_id=member_id,
        subtotal_cents=total_cents,
        total_cents=total_cents,
        payment_method=payment_method,
        status=status,
        sold_at=sold_at or datetime.now(timezone.utc),
    )
    session.add(sale)
    session.flush()
    session.add(
        SaleItem(
            sale_id=sale.id,
            product_id=product_id,
            product_name="Proteína",
            sku="PROT-1",
            quantity=2,
            unit_price_cents=total_cents // 2,
            line_total_cents=total_cents,
            location="Mostrador",
        )
    )
    session.commit()
    return sale.id


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _override(engine):
    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return override_session


def _receptor(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "rfc": "LOPA800101AAA",
        "legal_name": "Ana López",
        "tax_regime": "612",
        "postal_code": "06700",
        "cfdi_use": "G03",
        "email": "ana.lopez@correo.com.mx",
    }
    values.update(overrides)
    return values


def _invoice_payload(
    origin_type: str,
    origin_id: UUID,
    *,
    key: str = "invoice-key-1",
    **receptor_overrides: object,
) -> dict[str, object]:
    return {
        "origin_type": origin_type,
        "origin_id": str(origin_id),
        "idempotency_key": key,
        "receptor": _receptor(**receptor_overrides),
    }


def _prepare():
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, plan_id, payment_id = _seed_member_and_payment(session)
        product_id = _seed_product(session)
        sale_id = _seed_sale(session, member_id=member_id, product_id=product_id)
    app.dependency_overrides[get_session] = _override(engine)
    return engine, member_id, plan_id, payment_id, sale_id


def test_invoice_from_sale_splits_vat_and_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, member_id, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            created = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id),
            )
            assert created.status_code == 201, created.text
            body = created.json()
            invoice = body["invoice"]
            assert body["idempotent_replay"] is False
            assert invoice["status"] == "requested"
            assert invoice["folio_label"] == "A-000001"
            assert invoice["subtotal_cents"] == 10000
            assert invoice["tax_cents"] == 1600
            assert invoice["total_cents"] == 11600
            assert invoice["tax_rate_percent"] == 16
            assert invoice["payment_form"] == "01"
            assert invoice["member_name"] == "Ana López"
            assert invoice["items"][0]["description"] == "Proteína"
            assert invoice["items"][0]["quantity"] == 2
            assert invoice["items"][0]["subtotal_cents"] == 10000
            assert [event["event_type"] for event in invoice["events"]] == ["invoice_requested"]

            replay = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id),
            )
            assert replay.status_code == 201
            assert replay.json()["idempotent_replay"] is True
            assert replay.json()["invoice"]["id"] == invoice["id"]

            conflict = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id, rfc="XAXX010101000"),
            )
            assert conflict.status_code == 409

            duplicate = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id, key="another-key"),
            )
            assert duplicate.status_code == 409

            reception = _login(client, "reception@example.com", "reception-strong-password")
            listing = client.get("/admin/billing/invoices", headers=reception)
            assert listing.status_code == 200
            assert listing.json()["total"] == 1
            assert listing.json()["items"][0]["receptor_rfc"] == "LOPA800101AAA"

            detail = client.get(f"/admin/billing/invoices/{invoice['id']}", headers=reception)
            assert detail.status_code == 200
            assert detail.json()["origin_reference"].startswith("V-")

            summary = client.get("/admin/billing/summary", headers=reception)
            assert summary.status_code == 200
            assert summary.json()["requested"] == 1
            assert summary.json()["total"] == 1
    finally:
        app.dependency_overrides.clear()


def test_stamp_download_and_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            invoice = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id),
            ).json()["invoice"]
            invoice_id = invoice["id"]

            stamped = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert stamped.status_code == 200, stamped.text
            stamped_body = stamped.json()
            assert stamped_body["status"] == "stamped"
            assert stamped_body["is_simulated"] is True
            assert stamped_body["uuid"] is None
            assert stamped_body["provider"] == "simulated"
            assert stamped_body["provider_reference"].startswith("SIM-")
            assert stamped_body["stamped_at"] is not None
            assert [event["event_type"] for event in stamped_body["events"]] == [
                "invoice_requested",
                "invoice_stamped",
            ]

            replayed = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert replayed.status_code == 200
            assert replayed.json()["provider_reference"] == stamped_body["provider_reference"]

            xml = client.get(f"/admin/billing/invoices/{invoice_id}/xml", headers=accountant)
            assert xml.status_code == 200
            assert xml.headers["content-type"].startswith("application/xml")
            assert (
                'filename="CFDI-A-000001-simulada.xml"' in xml.headers["content-disposition"]
            )
            assert "<cfdi:Comprobante" in xml.text
            assert "SIMULACION" in xml.text
            assert 'Total="116.00"' in xml.text
            assert 'Rfc="LOPA800101AAA"' in xml.text
            assert 'TasaOCuota="0.160000"' in xml.text

            bad_reason = client.post(
                f"/admin/billing/invoices/{invoice_id}/cancel",
                headers=accountant,
                json={"reason_code": "01"},
            )
            assert bad_reason.status_code == 422

            cancelled = client.post(
                f"/admin/billing/invoices/{invoice_id}/cancel",
                headers=accountant,
                json={"reason_code": "02", "note": "Datos fiscales incorrectos"},
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            assert cancelled.json()["cancellation_reason_code"] == "02"
            assert cancelled.json()["cancelled_at"] is not None

            twice = client.post(
                f"/admin/billing/invoices/{invoice_id}/cancel",
                headers=accountant,
                json={"reason_code": "02"},
            )
            assert twice.status_code == 409
            cannot_restamp = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert cannot_restamp.status_code == 409

            replacement = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id, key="replacement-key"),
            )
            assert replacement.status_code == 201, replacement.text
            assert replacement.json()["invoice"]["folio_label"] == "A-000002"
    finally:
        app.dependency_overrides.clear()


def test_invoice_from_membership_payment_and_fiscal_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, member_id, _, payment_id, _ = _prepare()
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            profile = client.put(
                f"/admin/members/{member_id}/fiscal-profile",
                headers=reception,
                json=_receptor(),
            )
            assert profile.status_code == 200, profile.text
            assert profile.json()["rfc"] == "LOPA800101AAA"

            fetched = client.get(
                f"/admin/members/{member_id}/fiscal-profile", headers=reception
            )
            assert fetched.status_code == 200
            assert fetched.json()["cfdi_use"] == "G03"

            origins = client.get(
                "/admin/billing/origins",
                headers=reception,
                params={"origin_type": "membership_payment"},
            )
            assert origins.status_code == 200
            assert origins.json()["total"] == 1
            assert origins.json()["items"][0]["total_cents"] == 50000

            created = client.post(
                "/admin/billing/invoices",
                headers=reception,
                json=_invoice_payload("membership_payment", payment_id, key="payment-key"),
            )
            assert created.status_code == 201, created.text
            invoice = created.json()["invoice"]
            assert invoice["total_cents"] == 50000
            assert invoice["subtotal_cents"] == 43103
            assert invoice["tax_cents"] == 6897
            assert invoice["items"][0]["description"].startswith("Membresía Mensual")
            assert invoice["items"][0]["unit_name"] == "Servicio"
            assert invoice["member_name"] == "Ana López"

            after = client.get(
                "/admin/billing/origins",
                headers=reception,
                params={"origin_type": "membership_payment"},
            )
            assert after.json()["total"] == 0
    finally:
        app.dependency_overrides.clear()


def test_origins_only_lists_invoiceable_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _, _ = _seed_member_and_payment(session)
        product_id = _seed_product(session)
        normal = _seed_sale(session, member_id=member_id, product_id=product_id)
        account = _seed_sale(
            session, member_id=member_id, product_id=product_id, payment_method="account"
        )
        refunded = _seed_sale(
            session, member_id=member_id, product_id=product_id, status="refunded"
        )
        with_return = _seed_sale(session, member_id=member_id, product_id=product_id)
        session.add(
            SaleReturn(
                folio="D-20261023-ABC123",
                sale_id=with_return,
                refund_method="cash",
                total_refund_cents=11600,
                reason="Producto dañado",
                returned_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            origins = client.get(
                "/admin/billing/origins",
                headers=reception,
                params={"origin_type": "sale"},
            )
            assert origins.status_code == 200
            ids = {item["origin_id"] for item in origins.json()["items"]}
            assert ids == {str(normal)}
            assert str(account) not in ids
            assert str(refunded) not in ids
            assert str(with_return) not in ids

            by_folio = client.get(
                "/admin/billing/origins",
                headers=reception,
                params={"origin_type": "sale", "search": "V-2026"},
            )
            assert by_folio.json()["total"] == 1
    finally:
        app.dependency_overrides.clear()


def test_non_invoiceable_origins_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _, _ = _seed_member_and_payment(session)
        product_id = _seed_product(session)
        account = _seed_sale(
            session, member_id=member_id, product_id=product_id, payment_method="account"
        )
        refunded = _seed_sale(
            session, member_id=member_id, product_id=product_id, status="refunded"
        )
        with_return = _seed_sale(session, member_id=member_id, product_id=product_id)
        session.add(
            SaleReturn(
                folio="D-20261023-ABC124",
                sale_id=with_return,
                refund_method="cash",
                total_refund_cents=11600,
                reason="Producto dañado",
                returned_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            for origin_id in (account, refunded, with_return, uuid4()):
                response = client.post(
                    "/admin/billing/invoices",
                    headers=accountant,
                    json=_invoice_payload("sale", origin_id, key=f"key-{origin_id}"),
                )
                expected = 404 if origin_id not in (account, refunded, with_return) else 409
                assert response.status_code == expected, (origin_id, response.text)
    finally:
        app.dependency_overrides.clear()


def test_billing_permissions_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")

            assert client.get("/admin/billing/invoices", headers=trainer).status_code == 403
            assert (
                client.post(
                    "/admin/billing/invoices",
                    headers=trainer,
                    json=_invoice_payload("sale", sale_id, key="trainer-key"),
                ).status_code
                == 403
            )

            created = client.post(
                "/admin/billing/invoices",
                headers=reception,
                json=_invoice_payload("sale", sale_id, key="reception-key"),
            )
            assert created.status_code == 201
            invoice_id = created.json()["invoice"]["id"]
            assert (
                client.post(
                    f"/admin/billing/invoices/{invoice_id}/stamp", headers=reception
                ).status_code
                == 403
            )
            assert (
                client.post(
                    f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/admin/billing/invoices/{invoice_id}/cancel",
                    headers=reception,
                    json={"reason_code": "02"},
                ).status_code
                == 403
            )

            bad_rfc = client.post(
                "/admin/billing/invoices",
                headers=reception,
                json=_invoice_payload("sale", sale_id, key="bad-rfc", rfc="ABC"),
            )
            assert bad_rfc.status_code == 422
            bad_regime = client.post(
                "/admin/billing/invoices",
                headers=reception,
                json=_invoice_payload("sale", sale_id, key="bad-regime", tax_regime="999"),
            )
            assert bad_regime.status_code == 422
            bad_zip = client.post(
                "/admin/billing/invoices",
                headers=reception,
                json=_invoice_payload("sale", sale_id, key="bad-zip", postal_code="00000"),
            )
            assert bad_zip.status_code == 422
            bad_key = client.post(
                "/admin/billing/invoices",
                headers=reception,
                json=_invoice_payload("sale", sale_id, key="x" * 129),
            )
            assert bad_key.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_stamp_fails_without_a_configured_pac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAC_PROVIDER", raising=False)
    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            created = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id, key="no-pac"),
            )
            assert created.status_code == 201
            invoice_id = created.json()["invoice"]["id"]
            blocked = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert blocked.status_code == 503
            assert "PAC_PROVIDER" in blocked.json()["detail"]
            current = client.get(f"/admin/billing/invoices/{invoice_id}", headers=accountant)
            assert current.json()["status"] == "requested"
    finally:
        app.dependency_overrides.clear()


def test_invoice_pdf_is_only_available_after_stamping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            created = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id, key="pdf-key"),
            )
            assert created.status_code == 201, created.text
            invoice_id = created.json()["invoice"]["id"]

            assert client.get(
                f"/admin/billing/invoices/{invoice_id}/pdf", headers=trainer
            ).status_code == 403
            not_ready = client.get(
                f"/admin/billing/invoices/{invoice_id}/pdf", headers=reception
            )
            assert not_ready.status_code == 409
            assert "timbrada" in not_ready.json()["detail"]

            stamped = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert stamped.status_code == 200, stamped.text
            pdf = client.get(
                f"/admin/billing/invoices/{invoice_id}/pdf", headers=reception
            )
            assert pdf.status_code == 200, pdf.text
            assert pdf.headers["content-type"].startswith("application/pdf")
            assert (
                'filename="CFDI-A-000001-simulada.pdf"'
                in pdf.headers["content-disposition"]
            )
            assert pdf.content.startswith(b"%PDF")
            assert len(pdf.content) > 1000

            cancelled = client.post(
                f"/admin/billing/invoices/{invoice_id}/cancel",
                headers=accountant,
                json={"reason_code": "02", "note": "Prueba de representación impresa"},
            )
            assert cancelled.status_code == 200, cancelled.text
            after_cancel = client.get(
                f"/admin/billing/invoices/{invoice_id}/pdf", headers=reception
            )
            assert after_cancel.status_code == 200
            assert after_cancel.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()


def test_invoice_email_is_simulated_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    engine, member_id, _, _, sale_id = _prepare()
    with Session(engine) as session:
        extra_product = Product(sku="EXTRA-1", name="Extra", price_cents=1000)
        session.add(extra_product)
        session.commit()
        extra_sale_id = _seed_sale(
            session,
            member_id=member_id,
            product_id=extra_product.id,
            total_cents=1000,
        )
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            created = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id, key="mail-key"),
            )
            assert created.status_code == 201, created.text
            invoice_id = created.json()["invoice"]["id"]

            early = client.post(
                f"/admin/billing/invoices/{invoice_id}/send",
                headers=reception,
                json={},
            )
            assert early.status_code == 409
            assert client.post(
                f"/admin/billing/invoices/{invoice_id}/send",
                headers=trainer,
                json={},
            ).status_code == 403

            stamped = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert stamped.status_code == 200, stamped.text

            sent = client.post(
                f"/admin/billing/invoices/{invoice_id}/send",
                headers=reception,
                json={},
            )
            assert sent.status_code == 200, sent.text
            delivery = sent.json()
            assert delivery["status"] == "simulated"
            assert delivery["recipient"] == "ana.lopez@correo.com.mx"
            assert delivery["attachments"] == ["pdf", "xml"]

            detail = client.get(
                f"/admin/billing/invoices/{invoice_id}", headers=reception
            ).json()
            email_events = [
                event
                for event in detail["events"]
                if event["event_type"] == "invoice_email_sent"
            ]
            assert len(email_events) == 1
            assert email_events[0]["detail"]["recipient"] == "ana.lopez@correo.com.mx"
            assert email_events[0]["detail"]["delivery_status"] == "simulated"
            assert email_events[0]["detail"]["attachments"] == ["pdf", "xml"]

            override = client.post(
                f"/admin/billing/invoices/{invoice_id}/send",
                headers=reception,
                json={"email": "facturas@example.com"},
            )
            assert override.status_code == 200, override.text
            assert override.json()["recipient"] == "facturas@example.com"

            extra = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", extra_sale_id, key="mail-extra", email=None),
            )
            assert extra.status_code == 201, extra.text
            extra_id = extra.json()["invoice"]["id"]
            assert client.post(
                f"/admin/billing/invoices/{extra_id}/stamp", headers=accountant
            ).status_code == 200
            missing = client.post(
                f"/admin/billing/invoices/{extra_id}/send",
                headers=reception,
                json={},
            )
            assert missing.status_code == 422
            assert "correo" in missing.json()["detail"].lower()
            explicit = client.post(
                f"/admin/billing/invoices/{extra_id}/send",
                headers=reception,
                json={"email": "otro@example.com"},
            )
            assert explicit.status_code == 200, explicit.text
            assert explicit.json()["recipient"] == "otro@example.com"
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_invoice_email_transport_attaches_pdf_and_xml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    _, _, _, _, sale_id = _prepare()

    class FakeSMTP:
        instances: list["FakeSMTP"] = []

        def __init__(self, host: str, port: int, timeout: float) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.login_args: tuple[str, str] | None = None
            self.message = None
            FakeSMTP.instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

        def starttls(self, context=None) -> None:
            self.started_tls = True

        def login(self, username: str, password: str) -> None:
            self.login_args = (username, password)

        def send_message(self, message) -> None:
            self.message = message

    class FailingSMTP(FakeSMTP):
        def send_message(self, message) -> None:
            raise mailer.smtplib.SMTPException("smtp down")

    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            created = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", sale_id, key="smtp-key"),
            )
            assert created.status_code == 201, created.text
            invoice_id = created.json()["invoice"]["id"]
            assert client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            ).status_code == 200

            not_configured = client.post(
                f"/admin/billing/invoices/{invoice_id}/send",
                headers=accountant,
                json={},
            )
            assert not_configured.status_code == 503
            assert "SMTP_HOST" in not_configured.json()["detail"]

            monkeypatch.setenv("SMTP_HOST", "smtp.test")
            monkeypatch.setenv("SMTP_PORT", "2525")
            monkeypatch.setenv("SMTP_FROM", "club@example.test")
            monkeypatch.setenv("SMTP_USER", "smtp-user")
            monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
            monkeypatch.setenv("SMTP_USE_TLS", "true")
            monkeypatch.setenv("SMTP_USE_SSL", "false")
            monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

            sent = client.post(
                f"/admin/billing/invoices/{invoice_id}/send",
                headers=accountant,
                json={},
            )
            assert sent.status_code == 200, sent.text
            assert sent.json()["status"] == "sent"
            assert len(FakeSMTP.instances) == 1
            connection = FakeSMTP.instances[0]
            assert connection.host == "smtp.test"
            assert connection.port == 2525
            assert connection.started_tls is True
            assert connection.login_args == ("smtp-user", "smtp-secret")
            assert connection.message["From"] == "club@example.test"
            assert connection.message["To"] == "ana.lopez@correo.com.mx"
            attachments = {
                attachment.get_filename(): attachment
                for attachment in connection.message.iter_attachments()
            }
            assert set(attachments) == {
                "CFDI-A-000001-simulada.pdf",
                "CFDI-A-000001-simulada.xml",
            }
            assert attachments["CFDI-A-000001-simulada.pdf"].get_content().startswith(b"%PDF")
            xml_content = attachments["CFDI-A-000001-simulada.xml"].get_content()
            assert b"<cfdi:Comprobante" in xml_content
            assert b"SIMULACION" in xml_content

            monkeypatch.setattr(mailer.smtplib, "SMTP", FailingSMTP)
            failed = client.post(
                f"/admin/billing/invoices/{invoice_id}/send",
                headers=accountant,
                json={},
            )
            assert failed.status_code == 502, failed.text
            assert "No se pudo enviar" in failed.json()["detail"]

            detail = client.get(
                f"/admin/billing/invoices/{invoice_id}", headers=accountant
            ).json()
            failed_events = [
                event
                for event in detail["events"]
                if event["event_type"] == "invoice_email_failed"
            ]
            assert len(failed_events) == 2
            assert failed_events[0]["detail"]["reason"] == "not_configured"
            assert failed_events[1]["detail"]["reason"] == "transport"
            assert "smtp down" in failed_events[1]["detail"]["error"]
    finally:
        app.dependency_overrides.clear()


def _global_payload(year: int, month: int, *, key: str = "global-key-1") -> dict[str, object]:
    return {"year": year, "month": month, "idempotency_key": key}


def test_global_invoice_groups_public_sales_and_keeps_traceability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    monkeypatch.setenv("CFDI_SERIES", "A")
    monkeypatch.setenv("GYM_POSTAL_CODE", "01000")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    closed_month = datetime(2025, 1, 15, 18, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _, _ = _seed_member_and_payment(session)
        product_id = _seed_product(session)
        eligible_cash = _seed_sale(
            session,
            member_id=None,
            product_id=product_id,
            total_cents=11600,
            sold_at=closed_month,
        )
        eligible_card = _seed_sale(
            session,
            member_id=None,
            product_id=product_id,
            total_cents=5800,
            payment_method="card",
            sold_at=closed_month,
        )
        member_sale = _seed_sale(
            session,
            member_id=member_id,
            product_id=product_id,
            sold_at=closed_month,
        )
        account_sale = _seed_sale(
            session,
            member_id=None,
            product_id=product_id,
            total_cents=5800,
            payment_method="account",
            sold_at=closed_month,
        )
        refunded_sale = _seed_sale(
            session,
            member_id=None,
            product_id=product_id,
            status="refunded",
            sold_at=closed_month,
        )
        zero_sale = _seed_sale(
            session,
            member_id=None,
            product_id=product_id,
            total_cents=0,
            sold_at=closed_month,
        )
        returned_sale = _seed_sale(
            session,
            member_id=None,
            product_id=product_id,
            sold_at=closed_month,
        )
        individual_sale = _seed_sale(
            session,
            member_id=None,
            product_id=product_id,
            total_cents=2900,
            sold_at=closed_month,
        )
        session.add(
            SaleReturn(
                folio="D-20250115-ABC123",
                sale_id=returned_sale,
                refund_method="cash",
                total_refund_cents=11600,
                reason="Producto dañado",
                returned_at=closed_month,
            )
        )
        session.commit()
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")

            individual = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", individual_sale, key="individual-jan"),
            )
            assert individual.status_code == 201, individual.text

            assert (
                client.get(
                    "/admin/billing/global-invoices/eligible",
                    headers=trainer,
                    params={"year": 2025, "month": 1},
                ).status_code
                == 403
            )
            review = client.get(
                "/admin/billing/global-invoices/eligible",
                headers=reception,
                params={"year": 2025, "month": 1, "page_size": 1},
            )
            assert review.status_code == 200, review.text
            review_body = review.json()
            assert review_body["period_closed"] is True
            assert review_body["total_candidates"] == 8
            assert review_body["eligible_count"] == 2
            assert review_body["eligible_total_cents"] == 17400
            assert review_body["subtotal_cents"] == 15000
            assert review_body["tax_cents"] == 2400
            assert review_body["excluded_counts"] == {
                "returned": 2,
                "zero_total": 1,
                "account": 1,
                "member": 1,
                "individual_invoice": 1,
                "global_invoice": 0,
            }
            assert review_body["existing_invoice"] is None
            assert len(review_body["items"]) == 1
            assert review_body["items"][0]["sale_id"] in {
                str(eligible_cash),
                str(eligible_card),
            }
            second_page = client.get(
                "/admin/billing/global-invoices/eligible",
                headers=reception,
                params={"year": 2025, "month": 1, "page": 2, "page_size": 1},
            )
            assert len(second_page.json()["items"]) == 1

            assert (
                client.post(
                    "/admin/billing/global-invoices",
                    headers=reception,
                    json=_global_payload(2025, 1, key="reception-global"),
                ).status_code
                == 403
            )

            created = client.post(
                "/admin/billing/global-invoices",
                headers=accountant,
                json=_global_payload(2025, 1),
            )
            assert created.status_code == 201, created.text
            created_body = created.json()
            assert created_body["idempotent_replay"] is False
            invoice = created_body["invoice"]
            invoice_id = invoice["id"]
            assert invoice["origin_type"] == "global"
            assert invoice["origin_reference"] == "GLOBAL-2025-01"
            assert invoice["global_year"] == 2025
            assert invoice["global_month"] == 1
            assert invoice["status"] == "requested"
            assert invoice["receptor_rfc"] == "XAXX010101000"
            assert invoice["receptor_name"] == "PUBLICO EN GENERAL"
            assert invoice["receptor_tax_regime"] == "616"
            assert invoice["receptor_postal_code"] == "01000"
            assert invoice["receptor_cfdi_use"] == "S01"
            assert invoice["payment_form"] == "99"
            assert invoice["subtotal_cents"] == 15000
            assert invoice["tax_cents"] == 2400
            assert invoice["total_cents"] == 17400
            assert invoice["items"][0]["quantity"] == 2
            assert invoice["items"][0]["unit_price_cents"] == 7500
            assert invoice["items"][0]["unit_name"] == "Actividad"
            assert invoice["items"][0]["sat_unit_code"] == "ACT"
            assert "enero de 2025" in invoice["items"][0]["description"]
            assert len(invoice["global_sales"]) == 2
            assert {sale["sale_id"] for sale in invoice["global_sales"]} == {
                str(eligible_cash),
                str(eligible_card),
            }

            xml = client.get(
                f"/admin/billing/invoices/{invoice_id}/xml", headers=reception
            )
            assert xml.status_code == 200, xml.text
            assert '<cfdi:InformacionGlobal Periodicidad="03" Meses="01" Año="2025"' in xml.text
            assert 'Rfc="XAXX010101000"' in xml.text
            assert 'Nombre="PUBLICO EN GENERAL"' in xml.text
            assert 'RegimenFiscalReceptor="616"' in xml.text
            assert 'UsoCFDI="S01"' in xml.text
            assert 'ClaveUnidad="ACT"' in xml.text
            assert 'Cantidad="2"' in xml.text
            assert 'ValorUnitario="75.000000"' in xml.text
            assert 'Importe="150.00"' in xml.text

            replay = client.post(
                "/admin/billing/global-invoices",
                headers=accountant,
                json=_global_payload(2025, 1),
            )
            assert replay.status_code == 201, replay.text
            assert replay.json()["idempotent_replay"] is True
            assert replay.json()["invoice"]["id"] == invoice_id

            duplicate_period = client.post(
                "/admin/billing/global-invoices",
                headers=accountant,
                json=_global_payload(2025, 1, key="another-global-key"),
            )
            assert duplicate_period.status_code == 409
            assert "vigente" in duplicate_period.json()["detail"]

            overlap = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("sale", eligible_cash, key="overlap-key"),
            )
            assert overlap.status_code == 409
            assert "factura global" in overlap.json()["detail"]

            after = client.get(
                "/admin/billing/global-invoices/eligible",
                headers=reception,
                params={"year": 2025, "month": 1},
            ).json()
            assert after["eligible_count"] == 0
            assert after["excluded_counts"]["global_invoice"] == 2
            assert after["existing_invoice"]["invoice_id"] == invoice_id
            assert after["existing_invoice"]["status"] == "requested"

            origins = client.get(
                "/admin/billing/origins",
                headers=reception,
                params={"origin_type": "sale"},
            )
            assert origins.status_code == 200
            origin_ids = {item["origin_id"] for item in origins.json()["items"]}
            assert origin_ids == {str(member_sale)}
            assert str(eligible_cash) not in origin_ids
            assert str(eligible_card) not in origin_ids
            assert str(individual_sale) not in origin_ids
            assert str(account_sale) not in origin_ids
            assert str(refunded_sale) not in origin_ids
            assert str(zero_sale) not in origin_ids
            assert str(returned_sale) not in origin_ids

            stamped = client.post(
                f"/admin/billing/invoices/{invoice_id}/stamp", headers=accountant
            )
            assert stamped.status_code == 200, stamped.text
            assert stamped.json()["status"] == "stamped"
            assert stamped.json()["is_simulated"] is True
            pdf = client.get(
                f"/admin/billing/invoices/{invoice_id}/pdf", headers=reception
            )
            assert pdf.status_code == 200, pdf.text
            assert pdf.content.startswith(b"%PDF")

            cancelled = client.post(
                f"/admin/billing/invoices/{invoice_id}/cancel",
                headers=accountant,
                json={"reason_code": "02", "note": "Reemplazo de la factura global"},
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["global_sales"] == invoice["global_sales"]

            reopened = client.get(
                "/admin/billing/global-invoices/eligible",
                headers=reception,
                params={"year": 2025, "month": 1},
            ).json()
            assert reopened["eligible_count"] == 2
            assert reopened["excluded_counts"]["global_invoice"] == 0
            assert reopened["existing_invoice"] is None

            replacement = client.post(
                "/admin/billing/global-invoices",
                headers=accountant,
                json=_global_payload(2025, 1, key="global-replacement"),
            )
            assert replacement.status_code == 201, replacement.text
            replacement_invoice = replacement.json()["invoice"]
            assert replacement_invoice["id"] != invoice_id
            assert replacement_invoice["folio_label"] != invoice["folio_label"]
            assert len(replacement_invoice["global_sales"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_global_invoice_rejects_open_months_and_empty_periods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _prepare()
    try:
        with TestClient(app) as client:
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            current = club_date(datetime.now(timezone.utc))
            review = client.get(
                "/admin/billing/global-invoices/eligible",
                headers=reception,
                params={"year": current.year, "month": current.month},
            )
            assert review.status_code == 200, review.text
            assert review.json()["period_closed"] is False

            open_month = client.post(
                "/admin/billing/global-invoices",
                headers=accountant,
                json=_global_payload(current.year, current.month, key="open-month"),
            )
            assert open_month.status_code == 422
            assert "mes ya cerrado" in open_month.json()["detail"]

            empty = client.post(
                "/admin/billing/global-invoices",
                headers=accountant,
                json=_global_payload(2020, 1, key="empty-month"),
            )
            assert empty.status_code == 409
            assert "no tiene ventas" in empty.json()["detail"]

            assert (
                client.post(
                    "/admin/billing/global-invoices",
                    headers=accountant,
                    json=_global_payload(2024, 13, key="month-13"),
                ).status_code
                == 422
            )
            assert (
                client.get(
                    "/admin/billing/global-invoices/eligible",
                    headers=reception,
                    params={"year": 1999, "month": 1},
                ).status_code
                == 422
            )
    finally:
        app.dependency_overrides.clear()


def _stamped_sale_invoice(
    client: TestClient,
    headers: dict[str, str],
    sale_id: UUID,
    *,
    key: str = "credit-base",
) -> dict[str, object]:
    created = client.post(
        "/admin/billing/invoices",
        headers=headers,
        json=_invoice_payload("sale", sale_id, key=key),
    )
    assert created.status_code == 201, created.text
    invoice_id = created.json()["invoice"]["id"]
    stamped = client.post(
        f"/admin/billing/invoices/{invoice_id}/stamp", headers=headers
    )
    assert stamped.status_code == 200, stamped.text
    return stamped.json()


def _stamped_ppd_invoice(
    client: TestClient,
    headers: dict[str, str],
    sale_id: UUID,
    *,
    key: str = "ppd-base",
) -> dict[str, object]:
    payload = _invoice_payload("sale", sale_id, key=key)
    payload["payment_method"] = "PPD"
    payload["payment_form"] = "99"
    created = client.post("/admin/billing/invoices", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    invoice_id = created.json()["invoice"]["id"]
    stamped = client.post(
        f"/admin/billing/invoices/{invoice_id}/stamp", headers=headers
    )
    assert stamped.status_code == 200, stamped.text
    return stamped.json()


def _payment_payload(
    *,
    amount_cents: int,
    key: str,
    payment_form: str = "03",
    paid_on: str | None = None,
) -> dict[str, object]:
    return {
        "amount_cents": amount_cents,
        "payment_form": payment_form,
        "paid_on": paid_on or club_date(datetime.now(timezone.utc)).isoformat(),
        "idempotency_key": key,
    }


def test_credit_note_partial_then_full_controls_invoice_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id)
            base_id = str(base["id"])
            assert base["credit_balance_cents"] == 11600
            assert base["credited_cents"] == 0
            assert base["credit_notes"] == []

            created = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 5000,
                    "reason": "discount",
                    "note": "Descuento acordado",
                    "idempotency_key": "credit-note-1",
                },
            )
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["idempotent_replay"] is False
            note = body["invoice"]
            note_id = note["id"]
            assert note["origin_type"] == "credit_note"
            assert note["status"] == "requested"
            assert note["related_invoice_id"] == base_id
            assert note["related_invoice_folio_label"] == base["folio_label"]
            assert note["origin_reference"] == base["folio_label"]
            assert note["credit_note_reason"] == "discount"
            assert note["credit_note_note"] == "Descuento acordado"
            assert note["receptor_rfc"] == base["receptor_rfc"]
            assert note["receptor_email"] == base["receptor_email"]
            assert note["total_cents"] == 5000
            assert note["subtotal_cents"] == 4310
            assert note["tax_cents"] == 690
            assert note["items"][0]["description"].startswith("Nota de crédito")

            xml = client.get(
                f"/admin/billing/invoices/{note_id}/xml", headers=accountant
            )
            assert xml.status_code == 200
            assert 'TipoDeComprobante="E"' in xml.text
            assert "SIMULACION: la factura relacionada" in xml.text
            assert "TipoRelacion" not in xml.text

            stamped_note = client.post(
                f"/admin/billing/invoices/{note_id}/stamp", headers=accountant
            )
            assert stamped_note.status_code == 200, stamped_note.text
            assert stamped_note.json()["status"] == "stamped"
            assert [event["event_type"] for event in stamped_note.json()["events"]] == [
                "invoice_requested",
                "invoice_stamped",
            ]

            after_partial = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert after_partial["credited_cents"] == 5000
            assert after_partial["credit_balance_cents"] == 6600
            assert len(after_partial["credit_notes"]) == 1
            assert after_partial["credit_notes"][0]["folio_label"] == note["folio_label"]
            assert after_partial["credit_notes"][0]["status"] == "stamped"

            replay = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 5000,
                    "reason": "discount",
                    "note": "Descuento acordado",
                    "idempotency_key": "credit-note-1",
                },
            )
            assert replay.status_code == 201, replay.text
            assert replay.json()["idempotent_replay"] is True
            assert replay.json()["invoice"]["id"] == note_id

            conflict = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 4000,
                    "reason": "discount",
                    "note": "Descuento acordado",
                    "idempotency_key": "credit-note-1",
                },
            )
            assert conflict.status_code == 409

            over = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 6601,
                    "reason": "correction",
                    "idempotency_key": "credit-note-over",
                },
            )
            assert over.status_code == 422
            assert "saldo acreditable" in over.json()["detail"]

            full = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 6600,
                    "reason": "return",
                    "idempotency_key": "credit-note-full",
                },
            )
            assert full.status_code == 201, full.text
            full_note_id = full.json()["invoice"]["id"]
            full_note = full.json()["invoice"]
            assert full_note["subtotal_cents"] == 5690
            assert full_note["tax_cents"] == 910
            assert client.post(
                f"/admin/billing/invoices/{full_note_id}/stamp", headers=accountant
            ).status_code == 200

            exhausted = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert exhausted["credited_cents"] == 11600
            assert exhausted["credit_balance_cents"] == 0
            assert len(exhausted["credit_notes"]) == 2

            no_balance = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 1,
                    "reason": "other",
                    "idempotency_key": "credit-note-exhausted",
                },
            )
            assert no_balance.status_code == 409
            assert "totalmente acreditada" in no_balance.json()["detail"]

            summary = client.get("/admin/billing/summary", headers=accountant).json()
            assert summary["credit_notes"] == 2
            assert summary["credit_note_cents"] == 11600
            assert summary["stamped_cents"] == 11600
            assert summary["net_stamped_cents"] == 0

            notes_list = client.get(
                "/admin/billing/invoices",
                headers=accountant,
                params={"origin_type": "credit_note"},
            )
            assert notes_list.status_code == 200
            assert notes_list.json()["total"] == 2
            assert {item["related_invoice_id"] for item in notes_list.json()["items"]} == {
                base_id
            }
    finally:
        app.dependency_overrides.clear()


def test_credit_note_permissions_validation_and_related_restrictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, payment_id, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id)
            base_id = str(base["id"])

            denied = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=reception,
                json={
                    "amount_cents": 1000,
                    "reason": "discount",
                    "idempotency_key": "credit-denied",
                },
            )
            assert denied.status_code == 403

            assert client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 1000,
                    "reason": "refund",
                    "idempotency_key": "credit-bad-reason",
                },
            ).status_code == 422
            assert client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 0,
                    "reason": "discount",
                    "idempotency_key": "credit-zero",
                },
            ).status_code == 422
            assert client.post(
                f"/admin/billing/invoices/{uuid4()}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 1000,
                    "reason": "discount",
                    "idempotency_key": "credit-missing",
                },
            ).status_code == 404

            requested_payment = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload(
                    "membership_payment", payment_id, key="payment-requested"
                ),
            )
            assert requested_payment.status_code == 201, requested_payment.text
            payment_invoice_id = requested_payment.json()["invoice"]["id"]
            not_stamped = client.post(
                f"/admin/billing/invoices/{payment_invoice_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 1000,
                    "reason": "correction",
                    "idempotency_key": "credit-not-stamped",
                },
            )
            assert not_stamped.status_code == 409
            assert "timbrada" in not_stamped.json()["detail"]

            note = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 1000,
                    "reason": "correction",
                    "idempotency_key": "credit-note-chain",
                },
            )
            assert note.status_code == 201, note.text
            note_id = note.json()["invoice"]["id"]
            assert client.post(
                f"/admin/billing/invoices/{note_id}/stamp", headers=accountant
            ).status_code == 200
            chained = client.post(
                f"/admin/billing/invoices/{note_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 500,
                    "reason": "correction",
                    "idempotency_key": "credit-note-chain-2",
                },
            )
            assert chained.status_code == 409
            assert "otra nota de crédito" in chained.json()["detail"]
            assert client.post(
                f"/admin/billing/invoices/{note_id}/cancel",
                headers=accountant,
                json={"reason_code": "02", "note": "Prueba de cadena"},
            ).status_code == 200

            pending_note = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 100,
                    "reason": "other",
                    "idempotency_key": "credit-note-pending",
                },
            )
            assert pending_note.status_code == 201, pending_note.text
            pending_id = pending_note.json()["invoice"]["id"]
            cancelled_base = client.post(
                f"/admin/billing/invoices/{base_id}/cancel",
                headers=accountant,
                json={"reason_code": "02", "note": "Sin notas timbradas"},
            )
            assert cancelled_base.status_code == 200, cancelled_base.text
            cancelled_note = client.post(
                f"/admin/billing/invoices/{pending_id}/stamp", headers=accountant
            )
            assert cancelled_note.status_code == 409
            failed_note = client.get(
                f"/admin/billing/invoices/{pending_id}", headers=accountant
            ).json()
            assert failed_note["status"] == "failed"
            assert failed_note["events"][-1]["detail"]["code"] == "related_not_stamped"
            after_cancel = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 100,
                    "reason": "other",
                    "idempotency_key": "credit-after-cancel",
                },
            )
            assert after_cancel.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_credit_note_cancellation_restores_balance_and_unblocks_invoice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id)
            base_id = str(base["id"])
            note = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 3000,
                    "reason": "return",
                    "idempotency_key": "credit-cancel",
                },
            ).json()["invoice"]
            note_id = note["id"]
            assert client.post(
                f"/admin/billing/invoices/{note_id}/stamp", headers=accountant
            ).status_code == 200

            blocked = client.post(
                f"/admin/billing/invoices/{base_id}/cancel",
                headers=accountant,
                json={"reason_code": "02"},
            )
            assert blocked.status_code == 409
            assert "notas de crédito" in blocked.json()["detail"]

            cancelled_note = client.post(
                f"/admin/billing/invoices/{note_id}/cancel",
                headers=accountant,
                json={"reason_code": "02", "note": "Nota emitida por error"},
            )
            assert cancelled_note.status_code == 200, cancelled_note.text
            assert cancelled_note.json()["status"] == "cancelled"

            restored = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert restored["credited_cents"] == 0
            assert restored["credit_balance_cents"] == 11600
            assert restored["credit_notes"][0]["status"] == "cancelled"

            summary = client.get("/admin/billing/summary", headers=accountant).json()
            assert summary["credit_notes"] == 0
            assert summary["credit_note_cents"] == 0
            assert summary["net_stamped_cents"] == 11600

            cancelled_base = client.post(
                f"/admin/billing/invoices/{base_id}/cancel",
                headers=accountant,
                json={"reason_code": "02"},
            )
            assert cancelled_base.status_code == 200, cancelled_base.text
    finally:
        app.dependency_overrides.clear()


def test_credit_note_stamp_rechecks_the_available_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id)
            base_id = str(base["id"])
            first = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 11600,
                    "reason": "return",
                    "idempotency_key": "credit-race-1",
                },
            )
            assert first.status_code == 201, first.text
            second = client.post(
                f"/admin/billing/invoices/{base_id}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 11600,
                    "reason": "return",
                    "idempotency_key": "credit-race-2",
                },
            )
            assert second.status_code == 201, second.text
            first_id = first.json()["invoice"]["id"]
            second_id = second.json()["invoice"]["id"]

            assert client.post(
                f"/admin/billing/invoices/{first_id}/stamp", headers=accountant
            ).status_code == 200
            rejected = client.post(
                f"/admin/billing/invoices/{second_id}/stamp", headers=accountant
            )
            assert rejected.status_code == 422
            assert "saldo acreditable" in rejected.json()["detail"]

            failed = client.get(
                f"/admin/billing/invoices/{second_id}", headers=accountant
            ).json()
            assert failed["status"] == "failed"
            assert failed["events"][-1]["event_type"] == "invoice_stamp_failed"
            assert failed["events"][-1]["detail"]["code"] == "credit_balance_exceeded"
            base_detail = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert base_detail["credited_cents"] == 11600
            assert base_detail["credit_balance_cents"] == 0
    finally:
        app.dependency_overrides.clear()


def test_credit_note_xml_links_the_related_invoice_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id)
            base_uuid = "12345678-1234-1234-1234-123456789012"
            with Session(engine) as session:
                row = session.get(Invoice, UUID(str(base["id"])))
                assert row is not None
                row.uuid = base_uuid
                row.is_simulated = False
                session.add(row)
                session.commit()

            note = client.post(
                f"/admin/billing/invoices/{base['id']}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 1160,
                    "reason": "correction",
                    "idempotency_key": "credit-relation",
                },
            )
            assert note.status_code == 201, note.text
            note_id = note.json()["invoice"]["id"]
            xml = client.get(
                f"/admin/billing/invoices/{note_id}/xml", headers=accountant
            ).text
            assert 'TipoDeComprobante="E"' in xml
            assert 'TipoRelacion="01"' in xml
            assert f'UUID="{base_uuid}"' in xml
            assert "SIMULACION: la factura relacionada" not in xml

            stamped = client.post(
                f"/admin/billing/invoices/{note_id}/stamp", headers=accountant
            )
            assert stamped.status_code == 200, stamped.text
            assert f'UUID="{base_uuid}"' in client.get(
                f"/admin/billing/invoices/{note_id}/xml", headers=accountant
            ).text
    finally:
        app.dependency_overrides.clear()


def test_credit_note_pdf_and_email_are_labeled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    deliveries: list[dict[str, object]] = []

    def fake_send_email(**kwargs: object) -> str:
        deliveries.append(kwargs)
        return "simulated"

    monkeypatch.setattr(
        "app.modules.billing.service.send_email", fake_send_email
    )
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id)
            note = client.post(
                f"/admin/billing/invoices/{base['id']}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 2500,
                    "reason": "discount",
                    "idempotency_key": "credit-delivery",
                },
            ).json()["invoice"]
            note_id = note["id"]
            assert client.post(
                f"/admin/billing/invoices/{note_id}/stamp", headers=accountant
            ).status_code == 200

            pdf = client.get(
                f"/admin/billing/invoices/{note_id}/pdf", headers=accountant
            )
            assert pdf.status_code == 200, pdf.text
            assert pdf.content.startswith(b"%PDF")
            assert len(pdf.content) > 1000

            sent = client.post(
                f"/admin/billing/invoices/{note_id}/send", headers=accountant, json={}
            )
            assert sent.status_code == 200, sent.text
            assert sent.json()["status"] == "simulated"
            assert len(deliveries) == 1
            assert str(deliveries[0]["subject"]).startswith("Nota de crédito")
            assert "Factura relacionada" in str(deliveries[0]["body"])
            attachment_names = {
                attachment.filename for attachment in deliveries[0]["attachments"]
            }
            assert attachment_names == {
                f"CFDI-{note['series']}-{note['folio']:06d}-simulada.pdf",
                f"CFDI-{note['series']}-{note['folio']:06d}-simulada.xml",
            }
    finally:
        app.dependency_overrides.clear()


def test_ppd_invoice_forces_form_99_and_blocks_credit_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")

            payload = _invoice_payload("sale", sale_id, key="ppd-form")
            payload["payment_method"] = "PPD"
            payload["payment_form"] = "03"
            rejected = client.post(
                "/admin/billing/invoices", headers=accountant, json=payload
            )
            assert rejected.status_code == 422, rejected.text
            assert "99" in rejected.json()["detail"]

            payload["payment_form"] = "99"
            created = client.post(
                "/admin/billing/invoices", headers=accountant, json=payload
            )
            assert created.status_code == 201, created.text
            invoice = created.json()["invoice"]
            assert invoice["payment_method"] == "PPD"
            assert invoice["payment_form"] == "99"
            assert invoice["payment_status"] == "unpaid"
            assert invoice["payment_balance_cents"] == 11600
            assert invoice["events"][0]["detail"]["payment_method"] == "PPD"

            stamped = client.post(
                f"/admin/billing/invoices/{invoice['id']}/stamp", headers=accountant
            )
            assert stamped.status_code == 200, stamped.text
            assert stamped.json()["payment_method"] == "PPD"

            note = client.post(
                f"/admin/billing/invoices/{invoice['id']}/credit-notes",
                headers=accountant,
                json={
                    "amount_cents": 1000,
                    "reason": "correction",
                    "idempotency_key": "ppd-credit-note",
                },
            )
            assert note.status_code == 409, note.text
            assert "PPD" in note.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_ppd_payment_complement_partial_then_full_and_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_ppd_invoice(client, accountant, sale_id)
            base_id = str(base["id"])

            created = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=5000, key="ppd-payment-1"),
            )
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["idempotent_replay"] is False
            payment = body["payment"]
            assert payment["status"] == "requested"
            assert payment["folio_label"] == "P-000001"
            assert payment["partiality_number"] == 1
            assert payment["prior_balance_cents"] == 11600
            assert payment["outstanding_balance_cents"] == 6600
            assert payment["payment_form"] == "03"
            payment_id = payment["id"]

            replay = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=5000, key="ppd-payment-1"),
            )
            assert replay.status_code == 201
            assert replay.json()["idempotent_replay"] is True
            assert replay.json()["payment"]["id"] == payment_id
            conflict = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=4000, key="ppd-payment-1"),
            )
            assert conflict.status_code == 409

            requested = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert requested["paid_cents"] == 0
            assert requested["payment_balance_cents"] == 11600
            assert requested["payment_status"] == "unpaid"
            assert requested["payment_complements"][0]["status"] == "requested"

            stamped = client.post(
                f"/admin/billing/payment-complements/{payment_id}/stamp",
                headers=accountant,
            )
            assert stamped.status_code == 200, stamped.text
            stamped_payment = stamped.json()
            assert stamped_payment["status"] == "stamped"
            assert stamped_payment["partiality_number"] == 1
            assert stamped_payment["prior_balance_cents"] == 11600
            assert stamped_payment["outstanding_balance_cents"] == 6600
            assert stamped_payment["uuid"] is None
            assert stamped_payment["is_simulated"] is True
            assert [event["event_type"] for event in stamped_payment["events"]] == [
                "payment_requested",
                "payment_stamped",
            ]

            partial = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert partial["paid_cents"] == 5000
            assert partial["payment_balance_cents"] == 6600
            assert partial["payment_status"] == "partial"

            second = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=6600, key="ppd-payment-2"),
            )
            assert second.status_code == 201, second.text
            second_payment = second.json()["payment"]
            assert second_payment["partiality_number"] == 2
            assert second_payment["prior_balance_cents"] == 6600
            assert second_payment["outstanding_balance_cents"] == 0
            assert client.post(
                f"/admin/billing/payment-complements/{second_payment['id']}/stamp",
                headers=accountant,
            ).status_code == 200

            paid = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert paid["paid_cents"] == 11600
            assert paid["payment_balance_cents"] == 0
            assert paid["payment_status"] == "paid"

            extra = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=100, key="ppd-payment-extra"),
            )
            assert extra.status_code == 409
            assert "pagada en su totalidad" in extra.json()["detail"]

            blocked_cancel = client.post(
                f"/admin/billing/invoices/{base_id}/cancel",
                headers=accountant,
                json={"reason_code": "02"},
            )
            assert blocked_cancel.status_code == 409
            assert "complementos de pago" in blocked_cancel.json()["detail"]

            old_partiality = client.post(
                f"/admin/billing/payment-complements/{payment_id}/cancel",
                headers=accountant,
                json={"reason_code": "02"},
            )
            assert old_partiality.status_code == 409
            assert "última parcialidad" in old_partiality.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_ppd_payment_stamp_rechecks_balance_and_downloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_ppd_invoice(client, accountant, sale_id)
            base_id = str(base["id"])
            first = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=11600, key="ppd-race-1"),
            ).json()["payment"]
            second = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=11600, key="ppd-race-2"),
            ).json()["payment"]

            assert client.post(
                f"/admin/billing/payment-complements/{first['id']}/stamp",
                headers=accountant,
            ).status_code == 200
            rejected = client.post(
                f"/admin/billing/payment-complements/{second['id']}/stamp",
                headers=accountant,
            )
            assert rejected.status_code == 422, rejected.text
            assert "saldo pendiente de pago" in rejected.json()["detail"]

            failed = client.get(
                f"/admin/billing/payment-complements/{second['id']}",
                headers=accountant,
            ).json()
            assert failed["status"] == "failed"
            assert failed["events"][-1]["event_type"] == "payment_stamp_failed"
            assert failed["events"][-1]["detail"]["code"] == "payment_balance_exceeded"

            xml = client.get(
                f"/admin/billing/payment-complements/{first['id']}/xml",
                headers=accountant,
            )
            assert xml.status_code == 200, xml.text
            assert (
                f"PAGO-P-{first['folio']:06d}-simulada.xml"
                in xml.headers["content-disposition"]
            )
            assert 'TipoDeComprobante="P"' in xml.text
            assert 'UsoCFDI="CP01"' in xml.text
            assert '<pago20:Pagos Version="2.0">' in xml.text
            assert 'FormaDePagoP="03"' in xml.text
            assert 'Monto="116.00"' in xml.text
            assert 'NumParcialidad="1"' in xml.text
            assert 'ImpSaldoAnt="116.00"' in xml.text
            assert 'ImpPagado="116.00"' in xml.text
            assert 'ImpSaldoInsoluto="0.00"' in xml.text
            assert 'ImpuestoDR="002"' in xml.text
            assert 'TasaOCuotaDR="0.160000"' in xml.text
            assert "SIMULACION: la factura pagada" in xml.text
            assert "IdDocumento=" not in xml.text
            assert 'TipoRelacion="07"' not in xml.text

            pdf = client.get(
                f"/admin/billing/payment-complements/{first['id']}/pdf",
                headers=accountant,
            )
            assert pdf.status_code == 200, pdf.text
            assert pdf.content.startswith(b"%PDF")
            assert len(pdf.content) > 1000
            assert (
                f"PAGO-P-{first['folio']:06d}-simulada.pdf"
                in pdf.headers["content-disposition"]
            )
            assert client.get(
                f"/admin/billing/payment-complements/{second['id']}/pdf",
                headers=accountant,
            ).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_ppd_payment_xml_links_the_invoice_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_ppd_invoice(client, accountant, sale_id)
            base_uuid = "12345678-1234-1234-1234-123456789012"
            with Session(engine) as session:
                row = session.get(Invoice, UUID(str(base["id"])))
                assert row is not None
                row.uuid = base_uuid
                row.is_simulated = False
                session.add(row)
                session.commit()

            payment = client.post(
                f"/admin/billing/invoices/{base['id']}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=5000, key="ppd-uuid"),
            ).json()["payment"]
            assert client.post(
                f"/admin/billing/payment-complements/{payment['id']}/stamp",
                headers=accountant,
            ).status_code == 200

            xml = client.get(
                f"/admin/billing/payment-complements/{payment['id']}/xml",
                headers=accountant,
            ).text
            assert 'TipoDeComprobante="P"' in xml
            assert 'TipoRelacion="07"' in xml
            assert f'UUID="{base_uuid}"' in xml
            assert f'IdDocumento="{base_uuid}"' in xml
            assert 'UsoCFDI="CP01"' in xml
            assert "<pago20:ImpuestosP>" in xml
            assert "SIMULACION: la factura pagada" not in xml
    finally:
        app.dependency_overrides.clear()


def test_ppd_payment_cancellation_restores_balance_and_unblocks_invoice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    _, _, _, _, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_ppd_invoice(client, accountant, sale_id)
            base_id = str(base["id"])
            payment = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=5000, key="ppd-cancel"),
            ).json()["payment"]
            assert client.post(
                f"/admin/billing/payment-complements/{payment['id']}/stamp",
                headers=accountant,
            ).status_code == 200

            blocked = client.post(
                f"/admin/billing/invoices/{base_id}/cancel",
                headers=accountant,
                json={"reason_code": "02"},
            )
            assert blocked.status_code == 409
            assert "complementos de pago" in blocked.json()["detail"]

            cancelled = client.post(
                f"/admin/billing/payment-complements/{payment['id']}/cancel",
                headers=accountant,
                json={"reason_code": "02", "note": "Pago registrado por error"},
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            assert cancelled.json()["cancellation_note"] == "Pago registrado por error"

            restored = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert restored["paid_cents"] == 0
            assert restored["payment_balance_cents"] == 11600
            assert restored["payment_status"] == "unpaid"
            assert restored["payment_complements"][0]["status"] == "cancelled"

            assert client.get(
                f"/admin/billing/payment-complements/{payment['id']}/pdf",
                headers=accountant,
            ).status_code == 200
            released = client.post(
                f"/admin/billing/invoices/{base_id}/cancel",
                headers=accountant,
                json={"reason_code": "02"},
            )
            assert released.status_code == 200, released.text
    finally:
        app.dependency_overrides.clear()


def test_ppd_payment_permissions_and_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine, member_id, _, payment_id, sale_id = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            base = _stamped_ppd_invoice(client, accountant, sale_id)
            base_id = str(base["id"])

            denied = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=reception,
                json=_payment_payload(amount_cents=1000, key="ppd-reception"),
            )
            assert denied.status_code == 403

            payment = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=1000, key="ppd-permissions"),
            ).json()["payment"]
            payment_id_created = payment["id"]
            assert client.post(
                f"/admin/billing/payment-complements/{payment_id_created}/stamp",
                headers=accountant,
            ).status_code == 200

            assert client.get(
                f"/admin/billing/payment-complements/{payment_id_created}",
                headers=reception,
            ).status_code == 200
            assert client.get(
                f"/admin/billing/payment-complements/{payment_id_created}/xml",
                headers=reception,
            ).status_code == 200
            assert client.get(
                f"/admin/billing/payment-complements/{payment_id_created}/pdf",
                headers=reception,
            ).status_code == 200
            assert client.get(
                f"/admin/billing/payment-complements/{payment_id_created}",
                headers=trainer,
            ).status_code == 403
            assert client.post(
                f"/admin/billing/payment-complements/{payment_id_created}/stamp",
                headers=reception,
            ).status_code == 403
            assert client.post(
                f"/admin/billing/payment-complements/{payment_id_created}/cancel",
                headers=reception,
                json={"reason_code": "02"},
            ).status_code == 403

            invalid_form = client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(
                    amount_cents=1000, key="ppd-bad-form", payment_form="99"
                ),
            )
            assert invalid_form.status_code == 422, invalid_form.text
            future = (
                club_date(datetime.now(timezone.utc)) + timedelta(days=1)
            ).isoformat()
            assert client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(
                    amount_cents=1000, key="ppd-future", paid_on=future
                ),
            ).status_code == 422
            before_issue = (
                club_date(datetime.now(timezone.utc)) - timedelta(days=2)
            ).isoformat()
            assert client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(
                    amount_cents=1000, key="ppd-before", paid_on=before_issue
                ),
            ).status_code == 422
            assert client.post(
                f"/admin/billing/invoices/{base_id}/payment-complements",
                headers=accountant,
                json={
                    "amount_cents": 0,
                    "payment_form": "03",
                    "idempotency_key": "ppd-zero",
                },
            ).status_code == 422
            assert client.get(
                f"/admin/billing/payment-complements/{uuid4()}", headers=accountant
            ).status_code == 404

            with Session(engine) as session:
                product = session.exec(select(Product)).first()
                assert product is not None
                pending_sale_id = _seed_sale(
                    session, member_id=member_id, product_id=product.id
                )
            pending_payload = _invoice_payload(
                "sale", pending_sale_id, key="ppd-pending"
            )
            pending_payload["payment_method"] = "PPD"
            pending_payload["payment_form"] = "99"
            pending_invoice = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=pending_payload,
            ).json()["invoice"]
            not_stamped = client.post(
                f"/admin/billing/invoices/{pending_invoice['id']}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=1000, key="ppd-not-stamped"),
            )
            assert not_stamped.status_code == 409
            assert "timbrada" in not_stamped.json()["detail"]

            pue = client.post(
                "/admin/billing/invoices",
                headers=accountant,
                json=_invoice_payload("membership_payment", payment_id, key="ppd-pue"),
            )
            assert pue.status_code == 201, pue.text
            pue_id = pue.json()["invoice"]["id"]
            assert client.post(
                f"/admin/billing/invoices/{pue_id}/stamp", headers=accountant
            ).status_code == 200
            not_ppd = client.post(
                f"/admin/billing/invoices/{pue_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=1000, key="ppd-not-ppd"),
            )
            assert not_ppd.status_code == 409
            assert "PPD" in not_ppd.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_ppd_receivables_age_open_balances_and_pending_complements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine, member_id, _, _, first_sale_id = _prepare()
    try:
        with Session(engine) as session:
            product = session.exec(select(Product)).first()
            assert product is not None
            sale_ids = [first_sale_id] + [
                _seed_sale(session, member_id=member_id, product_id=product.id)
                for _ in range(4)
            ]
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            invoices = [
                _stamped_ppd_invoice(
                    client, accountant, sale_id, key=f"ppd-aging-{index}"
                )
                for index, sale_id in enumerate(sale_ids[:4])
            ]
            _stamped_sale_invoice(
                client, accountant, sale_ids[4], key="ppd-aging-pue"
            )

            now = datetime.now(timezone.utc)
            ages = [100, 75, 45, 10]
            with Session(engine) as session:
                for invoice, age in zip(invoices, ages):
                    row = session.get(Invoice, UUID(str(invoice["id"])))
                    assert row is not None
                    row.issued_at = now - timedelta(days=age)
                    row.stamped_at = now - timedelta(days=age)
                    session.add(row)
                session.commit()

            oldest_id = str(invoices[0]["id"])
            stamped_payment = client.post(
                f"/admin/billing/invoices/{oldest_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=2000, key="ppd-aging-stamped"),
            ).json()["payment"]
            assert stamped_payment["status"] == "requested"
            assert client.post(
                f"/admin/billing/payment-complements/{stamped_payment['id']}/stamp",
                headers=accountant,
            ).status_code == 200
            requested_payment = client.post(
                f"/admin/billing/invoices/{oldest_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=3000, key="ppd-aging-requested"),
            ).json()["payment"]
            assert requested_payment["status"] == "requested"

            response = client.get("/admin/billing/receivables", headers=accountant)
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == 4
            assert body["page"] == 1
            assert body["page_size"] == 20
            summary = body["summary"]
            assert summary["invoices"] == 4
            assert summary["total_cents"] == 46400
            assert summary["paid_cents"] == 2000
            assert summary["outstanding_cents"] == 44400
            assert summary["aging"] == {
                "current_cents": 11600,
                "days_31_60_cents": 11600,
                "days_61_90_cents": 11600,
                "over_90_cents": 9600,
            }
            assert summary["stamped_complements"] == 1
            assert summary["stamped_complement_cents"] == 2000
            assert summary["requested_complements"] == 1
            assert summary["requested_complement_cents"] == 3000
            assert summary["failed_complements"] == 0
            assert summary["failed_complement_cents"] == 0
            assert summary["oldest_stamped_at"] is not None
            assert summary["as_of"]

            oldest = body["items"][0]
            assert oldest["invoice_id"] == oldest_id
            assert oldest["age_days"] == 100
            assert oldest["aging_bucket"] == "over_90"
            assert oldest["total_cents"] == 11600
            assert oldest["paid_cents"] == 2000
            assert oldest["balance_cents"] == 9600
            assert oldest["stamped_complements"] == 1
            assert oldest["requested_complements"] == 1
            assert oldest["failed_complements"] == 0
            assert oldest["last_payment_on"] == club_date(now).isoformat()
            assert oldest["is_simulated"] is True

            over_90 = client.get(
                "/admin/billing/receivables",
                headers=accountant,
                params={"aging_bucket": "over_90"},
            ).json()
            assert over_90["total"] == 1
            assert over_90["items"][0]["invoice_id"] == oldest_id
            assert over_90["summary"]["invoices"] == 4

            searched = client.get(
                "/admin/billing/receivables",
                headers=accountant,
                params={"search": invoices[1]["origin_reference"]},
            ).json()
            assert searched["total"] == 1
            assert searched["items"][0]["invoice_id"] == invoices[1]["id"]

            paged = client.get(
                "/admin/billing/receivables",
                headers=accountant,
                params={"page": 2, "page_size": 2},
            ).json()
            assert paged["total"] == 4
            assert paged["page"] == 2
            assert len(paged["items"]) == 2

            current_id = str(invoices[3]["id"])
            settled = client.post(
                f"/admin/billing/invoices/{current_id}/payment-complements",
                headers=accountant,
                json=_payment_payload(amount_cents=11600, key="ppd-aging-settled"),
            ).json()["payment"]
            assert client.post(
                f"/admin/billing/payment-complements/{settled['id']}/stamp",
                headers=accountant,
            ).status_code == 200

            after = client.get("/admin/billing/receivables", headers=accountant).json()
            assert after["total"] == 3
            assert after["summary"]["invoices"] == 3
            assert after["summary"]["total_cents"] == 34800
            assert after["summary"]["paid_cents"] == 2000
            assert after["summary"]["outstanding_cents"] == 32800
            assert after["summary"]["aging"]["current_cents"] == 0
            assert after["summary"]["stamped_complements"] == 1
            assert after["summary"]["stamped_complement_cents"] == 2000
            assert after["summary"]["requested_complements"] == 1

            assert client.get(
                "/admin/billing/receivables", headers=trainer
            ).status_code == 403
            assert client.get(
                "/admin/billing/receivables",
                headers=accountant,
                params={"aging_bucket": "ancient"},
            ).status_code == 422
    finally:
        app.dependency_overrides.clear()


SAT_UUID = "6C3C0C87-5A34-46F3-BD37-7B79922A51E6"


class _StubPac:
    """Answers cancel and SAT queries; stamping stays with the simulated PAC."""

    provider = "finkok"

    def __init__(self) -> None:
        self.cancel_calls: list[dict[str, object]] = []
        self.status_calls: list[dict[str, object]] = []
        self.cancel_outcome = _pending_cancel()
        self.status_outcome = _sat_status(
            estado="Vigente", estatus="En proceso de cancelación"
        )

    def stamp(self, xml: str):  # pragma: no cover - only cancel/status are exercised
        raise AssertionError("El stub no timbra.")

    def cancel(self, *, uuid, reason_code, replacement_uuid):
        self.cancel_calls.append(
            {
                "uuid": uuid,
                "reason_code": reason_code,
                "replacement_uuid": replacement_uuid,
            }
        )
        return self.cancel_outcome

    def sat_status(self, *, uuid, receptor_rfc, total_cents):
        self.status_calls.append(
            {
                "uuid": uuid,
                "receptor_rfc": receptor_rfc,
                "total_cents": total_cents,
            }
        )
        return self.status_outcome


def _pending_cancel() -> CancellationOutcome:
    return CancellationOutcome(
        provider="finkok",
        accepted=False,
        detail={
            "status": "202",
            "message": "En proceso de cancelación",
            "estatus_cancelacion": "En proceso",
        },
        simulated=False,
    )


def _sat_status(*, estado: str, estatus: str) -> SatStatusOutcome:
    return SatStatusOutcome(
        provider="finkok",
        estado=estado,
        es_cancelable="Cancelable sin aceptación",
        estatus_cancelacion=estatus,
        codigo_estatus="S - Comprobante obtenido satisfactoriamente.",
        simulated=False,
    )


def _assign_sat_uuid(engine, invoice_id: object) -> None:
    """The simulated stamp leaves no UUID; a real comprobante has one."""

    with Session(engine) as session:
        invoice = session.get(Invoice, UUID(str(invoice_id)))
        assert invoice is not None
        invoice.uuid = SAT_UUID
        session.add(invoice)
        session.commit()


def test_pending_cancellation_is_tracked_then_confirmed_by_the_sat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine, _, _, _, sale_id = _prepare()
    pac = _StubPac()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id, key="sat-pending")
            base_id = str(base["id"])
            _assign_sat_uuid(engine, base_id)
            monkeypatch.setattr(billing_service, "pac_gateway", lambda: pac)

            cancelled = client.post(
                f"/admin/billing/invoices/{base_id}/cancel",
                headers=accountant,
                json={"reason_code": "02", "note": "Solicitud del socio"},
            )
            assert cancelled.status_code == 202, cancelled.text
            pending = cancelled.json()
            assert pending["status"] == "stamped"
            assert pending["cancellation_pending"] is True
            assert pending["cancellation_requested_at"] is not None
            assert pending["cancellation_checked_at"] is not None
            assert pending["cancellation_reason_code"] == "02"
            assert pending["cancellation_note"] == "Solicitud del socio"
            assert pending["cancelled_at"] is None
            assert pending["events"][-1]["event_type"] == "invoice_cancellation_pending"
            assert pac.cancel_calls == [
                {"uuid": SAT_UUID, "reason_code": "02", "replacement_uuid": None}
            ]

            filtered = client.get(
                "/admin/billing/invoices",
                headers=accountant,
                params={"cancellation_pending": "true"},
            ).json()
            assert filtered["total"] == 1
            assert filtered["items"][0]["id"] == base_id
            settled = client.get(
                "/admin/billing/invoices",
                headers=accountant,
                params={"cancellation_pending": "false"},
            ).json()
            assert settled["total"] == 0
            assert (
                client.get("/admin/billing/summary", headers=accountant).json()[
                    "pending_cancellations"
                ]
                == 1
            )

            still = client.post(
                f"/admin/billing/invoices/{base_id}/cancellation-check",
                headers=accountant,
            )
            assert still.status_code == 200, still.text
            still_body = still.json()
            assert still_body["sat_status"]["estado"] == "Vigente"
            assert still_body["invoice"]["status"] == "stamped"
            assert still_body["invoice"]["cancellation_pending"] is True
            assert pac.status_calls == [
                {
                    "uuid": SAT_UUID,
                    "receptor_rfc": "LOPA800101AAA",
                    "total_cents": 11600,
                }
            ]

            pac.status_outcome = _sat_status(estado="Cancelado", estatus="Cancelado")
            confirmed = client.post(
                f"/admin/billing/invoices/{base_id}/cancellation-check",
                headers=accountant,
            )
            assert confirmed.status_code == 200, confirmed.text
            body = confirmed.json()
            assert body["sat_status"]["estado"] == "Cancelado"
            assert body["invoice"]["status"] == "cancelled"
            assert body["invoice"]["cancellation_pending"] is False
            assert body["invoice"]["cancellation_requested_at"] is None
            assert body["invoice"]["cancellation_reason_code"] == "02"
            assert body["invoice"]["cancellation_note"] == "Solicitud del socio"
            assert body["invoice"]["cancelled_at"] is not None
            assert body["invoice"]["events"][-1]["event_type"] == (
                "invoice_cancellation_confirmed"
            )

            with Session(engine) as session:
                notices = session.exec(
                    select(MemberNotification).where(
                        MemberNotification.kind == "invoice_cancelled"
                    )
                ).all()
            assert len(notices) == 1
            assert str(notices[0].ref_id) == base_id

            after = client.get("/admin/billing/summary", headers=accountant).json()
            assert after["pending_cancellations"] == 0
            assert after["cancelled"] == 1
    finally:
        app.dependency_overrides.clear()


def test_cancellation_check_clears_the_request_when_the_sat_keeps_the_invoice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine, _, _, _, sale_id = _prepare()
    pac = _StubPac()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id, key="sat-cleared")
            base_id = str(base["id"])
            _assign_sat_uuid(engine, base_id)
            monkeypatch.setattr(billing_service, "pac_gateway", lambda: pac)

            assert client.post(
                f"/admin/billing/invoices/{base_id}/cancel",
                headers=accountant,
                json={"reason_code": "03", "note": "No se realizó la operación"},
            ).status_code == 202

            pac.status_outcome = _sat_status(estado="No Encontrado", estatus="")
            unknown = client.post(
                f"/admin/billing/invoices/{base_id}/cancellation-check",
                headers=accountant,
            )
            assert unknown.status_code == 502, unknown.text
            assert "no encontró" in unknown.json()["detail"]
            untouched = client.get(
                f"/admin/billing/invoices/{base_id}", headers=accountant
            ).json()
            assert untouched["cancellation_pending"] is True
            assert untouched["events"][-1]["event_type"] == "invoice_cancellation_pending"

            pac.status_outcome = _sat_status(estado="Vigente", estatus="No cancelado")
            checked = client.post(
                f"/admin/billing/invoices/{base_id}/cancellation-check",
                headers=accountant,
            )
            assert checked.status_code == 200, checked.text
            body = checked.json()
            assert body["invoice"]["status"] == "stamped"
            assert body["invoice"]["cancellation_pending"] is False
            assert body["invoice"]["cancellation_requested_at"] is None
            assert body["invoice"]["cancellation_reason_code"] is None
            assert body["invoice"]["cancellation_note"] is None
            last = body["invoice"]["events"][-1]
            assert last["event_type"] == "invoice_cancellation_cleared"
            assert last["detail"]["previous"] == {
                "reason_code": "03",
                "replacement_uuid": None,
                "note": "No se realizó la operación",
            }
            assert (
                client.get("/admin/billing/summary", headers=accountant).json()[
                    "pending_cancellations"
                ]
                == 0
            )
    finally:
        app.dependency_overrides.clear()


def test_cancellation_check_requires_manage_and_a_sat_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAC_PROVIDER", "simulated")
    engine, _, _, _, sale_id = _prepare()
    pac = _StubPac()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            base = _stamped_sale_invoice(client, accountant, sale_id, key="sat-guards")
            base_id = str(base["id"])
            monkeypatch.setattr(billing_service, "pac_gateway", lambda: pac)

            assert client.post(
                f"/admin/billing/invoices/{base_id}/cancellation-check",
                headers=reception,
            ).status_code == 403

            missing_uuid = client.post(
                f"/admin/billing/invoices/{base_id}/cancellation-check",
                headers=accountant,
            )
            assert missing_uuid.status_code == 409
            assert "UUID" in missing_uuid.json()["detail"]
            assert pac.status_calls == []

            unknown = client.post(
                f"/admin/billing/invoices/{uuid4()}/cancellation-check",
                headers=accountant,
            )
            assert unknown.status_code == 404
    finally:
        app.dependency_overrides.clear()
