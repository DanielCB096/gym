from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import Product, Sale, SaleItem
from app.modules.memberships.models import (
    Member,
    Membership,
    Payment,
    PaymentAttempt,
    Plan,
)
from app.modules.portal.invoices import (
    DOWNLOAD_LINK_LIFETIME,
    InvalidDownloadLink,
    list_member_invoices,
    verify_download_link,
)
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


def _seed_users(session: Session) -> None:
    ensure_default_access_control(session)
    for email, password, role in (
        ("accountant@example.com", "accountant-strong-password", "accountant"),
        ("trainer@example.com", "trainer-strong-password", "trainer"),
    ):
        register_user(session, email=email, password=password, role_codes=(role,))


def _seed_member(session: Session, *, email: str, first_name: str = "Ana") -> tuple[UUID, UUID]:
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


def _seed_sale(session: Session, *, member_id: UUID, name: str) -> UUID:
    product = Product(sku=f"SKU-{uuid4().hex[:8].upper()}", name=name, price_cents=11600)
    session.add(product)
    session.flush()
    sale = Sale(
        folio=f"V-{uuid4().hex[:8].upper()}",
        member_id=member_id,
        subtotal_cents=11600,
        total_cents=11600,
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
            product_name=name,
            sku=product.sku,
            quantity=2,
            unit_price_cents=5800,
            line_total_cents=11600,
            location="Mostrador",
        )
    )
    session.commit()
    return sale.id


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


def _receptor() -> dict[str, object]:
    return {
        "rfc": "LOPA800101AAA",
        "legal_name": "Ana López",
        "tax_regime": "612",
        "postal_code": "06700",
        "cfdi_use": "G03",
        "email": "ana.lopez@correo.com.mx",
    }


def _create_invoice(
    client: TestClient,
    headers: dict[str, str],
    origin_type: str,
    origin_id: UUID,
    key: str,
) -> str:
    response = client.post(
        "/admin/billing/invoices",
        headers=headers,
        json={
            "origin_type": origin_type,
            "origin_id": str(origin_id),
            "idempotency_key": key,
            "receptor": _receptor(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["invoice"]["id"]


def _stamp(client: TestClient, headers: dict[str, str], invoice_id: str) -> None:
    response = client.post(
        f"/admin/billing/invoices/{invoice_id}/stamp", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "stamped"


def test_member_invoices_scope_downloads_and_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("PAC_PROVIDER", "simulated")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        ana_id, ana_payment = _seed_member(session, email="ana@example.com")
        beto_id, _ = _seed_member(session, email="beto@example.com", first_name="Beto")
        ana_sale = _seed_sale(session, member_id=ana_id, name="Proteína")
        ana_pending_sale = _seed_sale(session, member_id=ana_id, name="Shaker")
        beto_sale = _seed_sale(session, member_id=beto_id, name="Guantes")

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            accountant = _login(
                client, "accountant@example.com", "accountant-strong-password"
            )
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            ana_headers = _member_headers(client, "ana@example.com")
            beto_headers = _member_headers(client, "beto@example.com")

            sale_invoice = _create_invoice(
                client, accountant, "sale", ana_sale, "sale-invoice"
            )
            _stamp(client, accountant, sale_invoice)
            payment_invoice = _create_invoice(
                client, accountant, "membership_payment", ana_payment, "payment-invoice"
            )
            _stamp(client, accountant, payment_invoice)
            pending_invoice = _create_invoice(
                client, accountant, "sale", ana_pending_sale, "pending-invoice"
            )
            beto_invoice = _create_invoice(
                client, accountant, "sale", beto_sale, "beto-invoice"
            )
            _stamp(client, accountant, beto_invoice)

            listing = client.get("/member/invoices", headers=ana_headers)
            assert listing.status_code == 200, listing.text
            body = listing.json()
            assert body["total"] == 3
            assert body["pages"] == 1
            by_id = {item["id"]: item for item in body["items"]}
            assert set(by_id) == {sale_invoice, payment_invoice, pending_invoice}
            assert beto_invoice not in by_id

            sale_item = by_id[sale_invoice]
            assert sale_item["status"] == "stamped"
            assert sale_item["origin_type"] == "sale"
            assert sale_item["folio_label"] == f"A-{sale_item['folio']:06d}"
            assert sale_item["total_cents"] == 11600
            assert sale_item["is_simulated"] is True
            assert sale_item["uuid"] is None
            assert sale_item["pdf_path"] and sale_item["xml_path"]
            assert "xml_content" not in sale_item
            assert "created_by" not in sale_item

            assert by_id[payment_invoice]["origin_type"] == "membership_payment"
            pending_item = by_id[pending_invoice]
            assert pending_item["status"] == "requested"
            assert pending_item["pdf_path"] is None
            assert pending_item["xml_path"] is None
            assert pending_item["uuid"] is None

            # Newest first: the pending invoice was requested last.
            assert body["items"][0]["id"] == pending_invoice

            page = client.get(
                "/member/invoices?page=2&page_size=2", headers=ana_headers
            )
            assert page.status_code == 200, page.text
            assert page.json()["total"] == 3
            assert page.json()["pages"] == 2
            assert len(page.json()["items"]) == 1

            beto_listing = client.get("/member/invoices", headers=beto_headers).json()
            assert beto_listing["total"] == 1
            assert beto_listing["items"][0]["id"] == beto_invoice

            pdf_path = sale_item["pdf_path"]
            xml_path = sale_item["xml_path"]
            assert pdf_path and xml_path

            pdf = client.get(pdf_path)
            assert pdf.status_code == 200, pdf.text
            assert pdf.headers["content-type"].startswith("application/pdf")
            assert pdf.headers["cache-control"] == "no-store"
            assert pdf.content.startswith(b"%PDF")

            xml = client.get(xml_path)
            assert xml.status_code == 200, xml.text
            assert xml.headers["content-type"].startswith("application/xml")
            assert "LOPA800101AAA" in xml.text

            # The unsigned or tampered URL is rejected.
            parsed = urlparse(pdf_path)
            query = parse_qs(parsed.query)
            tampered = f"{parsed.path}?exp={query['exp'][0]}&sig={'0' * 64}"
            assert client.get(tampered).status_code == 403
            assert client.get(parsed.path).status_code == 422

            # Staff tokens cannot use the member portal and vice versa.
            assert client.get("/member/invoices", headers=trainer).status_code == 401
            assert (
                client.get("/admin/billing/invoices", headers=ana_headers).status_code
                == 401
            )

        # Links carry their issue time: one signed for the past is rejected.
        with Session(engine) as session:
            expired_listing = list_member_invoices(
                session,
                ana_id,
                now=datetime.now(timezone.utc)
                - DOWNLOAD_LINK_LIFETIME
                - timedelta(minutes=1),
            )
            expired_item = next(
                item for item in expired_listing.items if str(item.id) == sale_invoice
            )
            parsed = urlparse(expired_item.pdf_path or "")
            query = parse_qs(parsed.query)
            with pytest.raises(InvalidDownloadLink):
                verify_download_link(
                    UUID(sale_invoice),
                    "pdf",
                    int(query["exp"][0]),
                    query["sig"][0],
                )

            # A signature for one kind cannot be replayed against the other.
            now = datetime.now(timezone.utc) + timedelta(seconds=1)
            valid_listing = list_member_invoices(session, ana_id, now=now)
            valid_item = next(
                item for item in valid_listing.items if str(item.id) == sale_invoice
            )
            parsed = urlparse(valid_item.pdf_path or "")
            query = parse_qs(parsed.query)
            with pytest.raises(InvalidDownloadLink):
                verify_download_link(
                    UUID(sale_invoice),
                    "xml",
                    int(query["exp"][0]),
                    query["sig"][0],
                    now=now,
                )
            verify_download_link(
                UUID(sale_invoice),
                "pdf",
                int(query["exp"][0]),
                query["sig"][0],
                now=now,
            )
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_member_invoices_empty_clamped_and_unknown(session: Session) -> None:
    ana_id, _ = _seed_member(session, email="ana@example.com")

    listing = list_member_invoices(session, ana_id)
    assert listing.total == 0
    assert listing.items == []
    assert listing.pages == 0

    clamped = list_member_invoices(session, ana_id, page=0, page_size=500)
    assert clamped.page == 1
    assert clamped.page_size == 50

    with pytest.raises(MemberPortalError):
        list_member_invoices(session, uuid4())
