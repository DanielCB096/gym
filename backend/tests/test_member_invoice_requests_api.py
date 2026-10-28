from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
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
from app.modules.portal.invoices import list_billable_origins
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


def _seed_sale(
    session: Session,
    *,
    member_id: UUID | None,
    name: str,
    payment_method: str = "cash",
    total_cents: int = 11600,
) -> UUID:
    product = Product(
        sku=f"SKU-{uuid4().hex[:8].upper()}", name=name, price_cents=total_cents
    )
    session.add(product)
    session.flush()
    sale = Sale(
        folio=f"V-{uuid4().hex[:8].upper()}",
        member_id=member_id,
        subtotal_cents=total_cents,
        total_cents=total_cents,
        payment_method=payment_method,
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
            quantity=1,
            unit_price_cents=total_cents,
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


def test_member_requests_invoice_for_own_origins(
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
        beto_id, beto_payment = _seed_member(
            session, email="beto@example.com", first_name="Beto"
        )
        ana_sale = _seed_sale(session, member_id=ana_id, name="Proteína")
        ana_ppd_sale = _seed_sale(session, member_id=ana_id, name="Shaker")
        ana_account_sale = _seed_sale(
            session, member_id=ana_id, name="Guantes", payment_method="account"
        )
        ana_stamped_sale = _seed_sale(session, member_id=ana_id, name="Cuerda")
        beto_sale = _seed_sale(session, member_id=beto_id, name="Tenis")
        walk_in_sale = _seed_sale(session, member_id=None, name="Agua")

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
            ana = _member_headers(client, "ana@example.com")
            beto = _member_headers(client, "beto@example.com")

            stamped_invoice = _create_invoice(
                client, accountant, "sale", ana_stamped_sale, "admin-stamped"
            )
            stamped = client.post(
                f"/admin/billing/invoices/{stamped_invoice}/stamp", headers=accountant
            )
            assert stamped.status_code == 200, stamped.text

            origins = client.get("/member/invoices/origins", headers=ana)
            assert origins.status_code == 200, origins.text
            body = origins.json()
            assert body["total"] == 3
            assert body["pages"] == 1
            ids = {item["origin_id"] for item in body["items"]}
            assert ids == {str(ana_sale), str(ana_ppd_sale), str(ana_payment)}
            assert str(ana_account_sale) not in ids
            assert str(ana_stamped_sale) not in ids
            assert str(walk_in_sale) not in ids
            assert str(beto_sale) not in ids
            by_type = {item["origin_type"]: item for item in body["items"]}
            assert by_type["membership_payment"]["description"].startswith("Membresía")
            assert by_type["sale"]["payment_method"] == "cash"

            only_sales = client.get(
                "/member/invoices/origins?origin_type=sale", headers=ana
            ).json()
            assert only_sales["total"] == 2
            only_payments = client.get(
                "/member/invoices/origins?origin_type=membership_payment", headers=ana
            ).json()
            assert only_payments["total"] == 1

            page = client.get(
                "/member/invoices/origins?page=2&page_size=2", headers=ana
            ).json()
            assert page["total"] == 3
            assert page["pages"] == 2
            assert len(page["items"]) == 1

            beto_origins = client.get("/member/invoices/origins", headers=beto).json()
            assert beto_origins["total"] == 2
            beto_ids = {item["origin_id"] for item in beto_origins["items"]}
            assert beto_ids == {str(beto_sale), str(beto_payment)}

            # The app is only available to members and the staff area to staff.
            assert (
                client.get("/member/invoices/origins", headers=trainer).status_code
                == 401
            )
            assert (
                client.get(
                    "/admin/billing/origins?origin_type=sale", headers=ana
                ).status_code
                == 401
            )

            empty_profile = client.get("/member/fiscal-profile", headers=ana)
            assert empty_profile.status_code == 200, empty_profile.text
            assert empty_profile.json() == {"profile": None}

            request_body = {
                "origin_type": "sale",
                "origin_id": str(ana_sale),
                "idempotency_key": "ana-sale-invoice",
                "receptor": _receptor(),
            }
            created = client.post("/member/invoices", headers=ana, json=request_body)
            assert created.status_code == 201, created.text
            created_body = created.json()
            assert created_body["idempotent_replay"] is False
            invoice = created_body["invoice"]
            assert invoice["status"] == "requested"
            assert invoice["origin_type"] == "sale"
            assert invoice["total_cents"] == 11600
            assert invoice["folio_label"].startswith("A-")
            assert invoice["pdf_path"] is None
            assert invoice["xml_path"] is None
            assert invoice["uuid"] is None

            profile = client.get("/member/fiscal-profile", headers=ana).json()["profile"]
            assert profile["rfc"] == "LOPA800101AAA"
            assert profile["legal_name"] == "Ana López"
            assert profile["cfdi_use"] == "G03"
            assert profile["email"] == "ana.lopez@correo.com.mx"
            assert profile["updated_at"] is not None

            replay = client.post("/member/invoices", headers=ana, json=request_body)
            assert replay.status_code == 201, replay.text
            assert replay.json()["idempotent_replay"] is True
            assert replay.json()["invoice"]["id"] == invoice["id"]

            reused_key = client.post(
                "/member/invoices",
                headers=ana,
                json={**request_body, "origin_id": str(ana_ppd_sale)},
            )
            assert reused_key.status_code == 409, reused_key.text

            again = client.post(
                "/member/invoices",
                headers=ana,
                json={**request_body, "idempotency_key": "ana-sale-again"},
            )
            assert again.status_code == 409, again.text

            foreign = client.post(
                "/member/invoices",
                headers=ana,
                json={
                    "origin_type": "sale",
                    "origin_id": str(beto_sale),
                    "idempotency_key": "foreign-sale",
                    "receptor": _receptor(),
                },
            )
            assert foreign.status_code == 404, foreign.text

            foreign_payment = client.post(
                "/member/invoices",
                headers=ana,
                json={
                    "origin_type": "membership_payment",
                    "origin_id": str(beto_payment),
                    "idempotency_key": "foreign-payment",
                    "receptor": _receptor(),
                },
            )
            assert foreign_payment.status_code == 404, foreign_payment.text

            account_origin = client.post(
                "/member/invoices",
                headers=ana,
                json={
                    "origin_type": "sale",
                    "origin_id": str(ana_account_sale),
                    "idempotency_key": "account-sale",
                    "receptor": _receptor(),
                },
            )
            assert account_origin.status_code == 409, account_origin.text

            # The request event records that it came from the member app.
            admin_detail = client.get(
                f"/admin/billing/invoices/{invoice['id']}", headers=accountant
            ).json()
            assert admin_detail["origin_reference"].startswith("V-")
            assert admin_detail["created_by"] is None
            assert admin_detail["events"][0]["event_type"] == "invoice_requested"
            assert admin_detail["events"][0]["detail"]["channel"] == "member_app"
            assert admin_detail["events"][0]["actor_id"] is None

            invalid_ppd = client.post(
                "/member/invoices",
                headers=ana,
                json={
                    "origin_type": "sale",
                    "origin_id": str(ana_ppd_sale),
                    "idempotency_key": "ppd-bad-form",
                    "payment_method": "PPD",
                    "payment_form": "03",
                    "receptor": _receptor(),
                },
            )
            assert invalid_ppd.status_code == 422, invalid_ppd.text

            ppd = client.post(
                "/member/invoices",
                headers=ana,
                json={
                    "origin_type": "sale",
                    "origin_id": str(ana_ppd_sale),
                    "idempotency_key": "ppd-sale",
                    "payment_method": "PPD",
                    "receptor": _receptor(),
                },
            )
            assert ppd.status_code == 201, ppd.text
            assert ppd.json()["invoice"]["payment_method"] == "PPD"
            assert ppd.json()["invoice"]["payment_form"] == "99"

            payment_request = client.post(
                "/member/invoices",
                headers=ana,
                json={
                    "origin_type": "membership_payment",
                    "origin_id": str(ana_payment),
                    "idempotency_key": "ana-payment-invoice",
                    "receptor": _receptor(),
                },
            )
            assert payment_request.status_code == 201, payment_request.text
            assert (
                payment_request.json()["invoice"]["origin_type"]
                == "membership_payment"
            )
            assert payment_request.json()["invoice"]["total_cents"] == 50000

            remaining = client.get("/member/invoices/origins", headers=ana).json()
            assert remaining["total"] == 0
            assert remaining["pages"] == 0

            listing = client.get("/member/invoices", headers=ana).json()
            assert listing["total"] == 4

            # The member still cannot ask for an origin that belongs to somebody else.
            stolen_payment = client.post(
                "/member/invoices",
                headers=beto,
                json={
                    "origin_type": "membership_payment",
                    "origin_id": str(ana_payment),
                    "idempotency_key": "stolen-payment",
                    "receptor": _receptor(),
                },
            )
            assert stolen_payment.status_code == 404, stolen_payment.text

            bad_rfc = client.post(
                "/member/invoices",
                headers=ana,
                json={
                    "origin_type": "sale",
                    "origin_id": str(ana_sale),
                    "idempotency_key": "bad-rfc",
                    "receptor": {**_receptor(), "rfc": "ABC"},
                },
            )
            assert bad_rfc.status_code == 422, bad_rfc.text
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_billable_origins_empty_clamped_and_unknown(session: Session) -> None:
    ana_id, payment_id = _seed_member(session, email="ana@example.com")

    listing = list_billable_origins(session, ana_id)
    assert listing.total == 1
    assert listing.items[0].origin_id == payment_id
    assert listing.items[0].origin_type == "membership_payment"

    clamped = list_billable_origins(session, ana_id, page=0, page_size=500)
    assert clamped.page == 1
    assert clamped.page_size == 50

    filtered = list_billable_origins(session, ana_id, origin_type="sale")
    assert filtered.total == 0
    assert filtered.items == []
    assert filtered.pages == 0

    with pytest.raises(MemberPortalError):
        list_billable_origins(session, ana_id, origin_type="credit_note")

    with pytest.raises(MemberPortalError):
        list_billable_origins(session, uuid4())
