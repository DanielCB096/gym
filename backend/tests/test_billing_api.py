from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

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
    member_id: UUID,
    product_id: UUID,
    total_cents: int = 11600,
    payment_method: str = "cash",
    status: str = "completed",
) -> UUID:
    sale = Sale(
        folio=f"V-20261023-{uuid4().hex[:6].upper()}",
        member_id=member_id,
        subtotal_cents=total_cents,
        total_cents=total_cents,
        payment_method=payment_method,
        status=status,
        sold_at=datetime.now(timezone.utc),
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
