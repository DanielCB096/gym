from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import mailer
from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import Product, Sale, SaleItem, SaleReturn
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
