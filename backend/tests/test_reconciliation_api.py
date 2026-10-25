from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import (
    MemberAccountPayment,
    Product,
    Sale,
    SaleItem,
    SaleReturn,
)
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
    ):
        register_user(session, email=email, password=password, role_codes=(role,))


def _seed_transfer_payment(
    session: Session, *, amount_cents: int = 50000, paid_at: datetime | None = None
) -> tuple[UUID, UUID, UUID]:
    now = paid_at or datetime.now(timezone.utc)
    member = Member(first_name="Ana", last_name="López", email="ana@example.test", status="active")
    plan = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=amount_cents)
    session.add_all([member, plan])
    session.flush()
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
        method="transfer",
        idempotency_key=f"attempt-{uuid4()}",
        request_fingerprint="f" * 64,
        attempt_number=1,
        amount_cents=amount_cents,
        status="succeeded",
        due_at=now,
    )
    session.add(attempt)
    session.flush()
    payment = Payment(
        payment_attempt_id=attempt.id,
        member_id=member.id,
        membership_id=membership.id,
        amount_cents=amount_cents,
        currency="MXN",
        method="transfer",
        paid_at=now,
        period_starts_at=now,
        period_ends_at=now + timedelta(days=30),
    )
    session.add(payment)
    session.commit()
    return member.id, plan.id, payment.id


def _seed_credit_sale(
    session: Session,
    *,
    member_id: UUID,
    amount_cents: int = 11600,
    sold_at: datetime | None = None,
) -> UUID:
    now = sold_at or datetime.now(timezone.utc)
    product = Product(sku=f"PROT-{uuid4().hex[:4]}", name="Proteína", price_cents=amount_cents)
    session.add(product)
    session.flush()
    sale = Sale(
        folio=f"V-20261025-{uuid4().hex[:6].upper()}",
        member_id=member_id,
        subtotal_cents=amount_cents,
        total_cents=amount_cents,
        payment_method="transfer",
        status="completed",
        sold_at=now,
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
            unit_price_cents=amount_cents,
            line_total_cents=amount_cents,
            location="Mostrador",
        )
    )
    session.commit()
    return sale.id


def _seed_account_payment(session: Session, *, member_id: UUID, amount_cents: int = 35000) -> UUID:
    payment = MemberAccountPayment(
        member_id=member_id,
        method="transfer",
        amount_cents=amount_cents,
        paid_at=datetime.now(timezone.utc),
    )
    session.add(payment)
    session.commit()
    return payment.id


def _seed_return(
    session: Session, *, sale_id: UUID, member_id: UUID, amount_cents: int = 2000
) -> UUID:
    sale_return = SaleReturn(
        folio=f"D-20261025-{uuid4().hex[:4].upper()}",
        sale_id=sale_id,
        member_id=member_id,
        refund_method="transfer",
        total_refund_cents=amount_cents,
        reason="Producto defectuoso",
        returned_at=datetime.now(timezone.utc),
    )
    session.add(sale_return)
    session.commit()
    return sale_return.id


def _prepare():
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _, payment_id = _seed_transfer_payment(session)
        sale_id = _seed_credit_sale(session, member_id=member_id)
        account_payment_id = _seed_account_payment(session, member_id=member_id)
        return_id = _seed_return(session, sale_id=sale_id, member_id=member_id)
    app.dependency_overrides[get_session] = _override(engine)
    return engine, {
        "member_id": member_id,
        "payment_id": payment_id,
        "sale_id": sale_id,
        "account_payment_id": account_payment_id,
        "return_id": return_id,
    }


def _override(engine):
    def override_session():
        with Session(engine) as session:
            yield session

    return override_session


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_account(client: TestClient, headers: dict[str, str], name: str = "BBVA Operación") -> dict:
    response = client.post(
        "/admin/finance/bank-accounts",
        headers=headers,
        json={
            "name": name,
            "bank_name": "BBVA",
            "account_last4": "4821",
            "currency": "MXN",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _import(client: TestClient, headers: dict[str, str], account_id: str, rows: list[dict]) -> dict:
    response = client.post(
        f"/admin/finance/bank-accounts/{account_id}/movements",
        headers=headers,
        json={"rows": rows},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_bank_accounts_permissions_and_status() -> None:
    engine, _ = _prepare()
    try:
        with TestClient(app) as client:
            owner = _login(client, "owner@example.com", "owner-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")

            account = _create_account(client, accountant)
            assert account["name"] == "BBVA Operación"
            assert account["status"] == "active"
            assert account["movement_count"] == 0

            duplicate = client.post(
                "/admin/finance/bank-accounts",
                headers=owner,
                json={
                    "name": "bbva operación",
                    "bank_name": "BBVA",
                    "account_last4": "9999",
                    "currency": "MXN",
                },
            )
            assert duplicate.status_code == 409

            invalid = client.post(
                "/admin/finance/bank-accounts",
                headers=owner,
                json={
                    "name": "Cuenta inválida",
                    "bank_name": "BBVA",
                    "account_last4": "12AB",
                    "currency": "MXN",
                },
            )
            assert invalid.status_code == 422

            assert client.get("/admin/finance/bank-accounts", headers=reception).status_code == 403
            assert client.get("/admin/finance/bank-accounts", headers=manager).status_code == 200
            forbidden = client.post(
                "/admin/finance/bank-accounts",
                headers=manager,
                json={
                    "name": "Cuenta de gerencia",
                    "bank_name": "Banorte",
                    "account_last4": "1111",
                    "currency": "MXN",
                },
            )
            assert forbidden.status_code == 403

            second = _create_account(client, owner, name="Banorte Nómina")
            assert second["status"] == "active"
            listing = client.get("/admin/finance/bank-accounts", headers=manager)
            assert listing.status_code == 200
            assert [item["name"] for item in listing.json()["items"]] == [
                "Banorte Nómina",
                "BBVA Operación",
            ]

            deactivated = client.patch(
                f"/admin/finance/bank-accounts/{account['id']}",
                headers=accountant,
                json={"status": "inactive"},
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["status"] == "inactive"

            rejected = client.post(
                f"/admin/finance/bank-accounts/{account['id']}/movements",
                headers=accountant,
                json={
                    "rows": [
                        {
                            "occurred_on": "2026-10-24",
                            "amount_cents": 10000,
                            "reference": "SPEI",
                        }
                    ]
                },
            )
            assert rejected.status_code == 409
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_import_is_idempotent_and_rejects_invalid_batches() -> None:
    engine, _ = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            account = _create_account(client, accountant)
            rows = [
                {
                    "occurred_on": "2026-10-24",
                    "amount_cents": 50000,
                    "reference": "SPEI ANA LOPEZ",
                    "description": "Depósito de socio",
                },
                {
                    "occurred_on": "2026-10-24",
                    "amount_cents": 50000,
                    "reference": "SPEI ANA LOPEZ",
                    "description": "Depósito de socio",
                },
                {
                    "occurred_on": "2026-10-23",
                    "amount_cents": -2000,
                    "reference": "DEVOLUCION",
                    "description": "Reembolso",
                },
            ]
            first = _import(client, accountant, account["id"], rows)
            assert first == {"imported": 2, "duplicates": 1, "total_rows": 3}

            replay = _import(client, accountant, account["id"], rows)
            assert replay == {"imported": 0, "duplicates": 3, "total_rows": 3}

            invalid = client.post(
                f"/admin/finance/bank-accounts/{account['id']}/movements",
                headers=accountant,
                json={
                    "rows": [
                        {"occurred_on": "2026-10-24", "amount_cents": 1000, "reference": "OK"},
                        {"occurred_on": "2026-10-24", "amount_cents": 0, "reference": "CERO"},
                    ]
                },
            )
            assert invalid.status_code == 422
            assert "Fila 2" in invalid.json()["detail"]

            listing = client.get("/admin/finance/bank-movements", headers=accountant)
            assert listing.status_code == 200
            payload = listing.json()
            assert payload["total"] == 2
            assert payload["summary"]["pending"] == 2
            assert payload["summary"]["inflow_cents"] == 50000
            assert payload["summary"]["outflow_cents"] == -2000
            assert payload["items"][0]["occurred_on"] == "2026-10-24"
            assert payload["items"][0]["status"] == "pending"
            assert payload["items"][0]["suggestion_count"] >= 1

            filtered = client.get(
                "/admin/finance/bank-movements?status=pending&search=devolucion",
                headers=accountant,
            )
            assert filtered.status_code == 200
            assert filtered.json()["total"] == 1
            assert filtered.json()["items"][0]["amount_cents"] == -2000

            manager = _login(client, "manager@example.com", "manager-strong-password")
            forbidden = client.post(
                f"/admin/finance/bank-accounts/{account['id']}/movements",
                headers=manager,
                json={"rows": [{"occurred_on": "2026-10-24", "amount_cents": 1}]},
            )
            assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_membership_payment_suggestion_match_unmatch_and_conflict() -> None:
    engine, ids = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            account = _create_account(client, accountant)
            _import(
                client,
                accountant,
                account["id"],
                [
                    {
                        "occurred_on": "2026-10-24",
                        "amount_cents": 50000,
                        "reference": "SPEI ANA LOPEZ",
                        "description": "Pago de membresía",
                    }
                ],
            )
            listing = client.get("/admin/finance/bank-movements", headers=accountant).json()
            movement = listing["items"][0]
            assert movement["suggestion_count"] >= 1
            assert "Ana" in movement["suggested_label"]

            detail = client.get(
                f"/admin/finance/bank-movements/{movement['id']}", headers=accountant
            )
            assert detail.status_code == 200
            candidates = detail.json()["candidates"]
            assert candidates[0]["source"] == "membership_payment"
            assert candidates[0]["source_id"] == str(ids["payment_id"])
            assert candidates[0]["amount_match"] is True

            match = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/match",
                headers=accountant,
                json={"source": "membership_payment", "source_id": str(ids["payment_id"])},
            )
            assert match.status_code == 200, match.text
            matched = match.json()
            assert matched["status"] == "reconciled"
            assert matched["matched_id"] == str(ids["payment_id"])
            assert matched["difference_cents"] is None
            assert [event["event_type"] for event in matched["events"]] == [
                "imported",
                "matched",
            ]

            _import(
                client,
                accountant,
                account["id"],
                [
                    {
                        "occurred_on": "2026-10-25",
                        "amount_cents": 50000,
                        "reference": "SPEI ANA LOPEZ",
                    }
                ],
            )
            second = client.get("/admin/finance/bank-movements", headers=accountant).json()["items"][0]
            second_detail = client.get(
                f"/admin/finance/bank-movements/{second['id']}", headers=accountant
            ).json()
            assert second_detail["candidates"] == []
            conflict = client.post(
                f"/admin/finance/bank-movements/{second['id']}/match",
                headers=accountant,
                json={"source": "membership_payment", "source_id": str(ids["payment_id"])},
            )
            assert conflict.status_code == 409

            unmatch = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/unmatch",
                headers=accountant,
                json={"reason": "Se aplicó a otra línea"},
            )
            assert unmatch.status_code == 200
            assert unmatch.json()["status"] == "pending"
            assert unmatch.json()["matched_id"] is None
            assert unmatch.json()["events"][-1]["event_type"] == "unmatched"

            rematch = client.post(
                f"/admin/finance/bank-movements/{second['id']}/match",
                headers=accountant,
                json={"source": "membership_payment", "source_id": str(ids["payment_id"])},
            )
            assert rematch.status_code == 200
            assert rematch.json()["status"] == "reconciled"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_sale_and_return_matching_uses_direction_and_reference() -> None:
    engine, ids = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            account = _create_account(client, accountant)
            sale = client.get(f"/admin/sales", headers=accountant)
            assert sale.status_code == 200
            sale_folio = sale.json()["items"][0]["folio"]
            returns = client.get("/admin/sales/returns", headers=accountant)
            assert returns.status_code == 200
            return_folio = returns.json()["items"][0]["folio"]

            _import(
                client,
                accountant,
                account["id"],
                [
                    {
                        "occurred_on": "2026-10-24",
                        "amount_cents": 11600,
                        "reference": f"DEP {sale_folio}",
                    },
                    {
                        "occurred_on": "2026-10-24",
                        "amount_cents": -2000,
                        "reference": f"DEV {return_folio}",
                    },
                ],
            )
            listing = client.get("/admin/finance/bank-movements", headers=accountant).json()
            by_amount = {item["amount_cents"]: item for item in listing["items"]}
            deposit = by_amount[11600]
            refund = by_amount[-2000]

            deposit_detail = client.get(
                f"/admin/finance/bank-movements/{deposit['id']}", headers=accountant
            ).json()
            sources = [candidate["source"] for candidate in deposit_detail["candidates"]]
            assert "sale" in sources
            assert "membership_payment" not in sources

            deposited = client.post(
                f"/admin/finance/bank-movements/{deposit['id']}/match",
                headers=accountant,
                json={"source": "sale", "source_id": str(ids["sale_id"])},
            )
            assert deposited.status_code == 200
            assert deposited.json()["status"] == "reconciled"

            refund_detail = client.get(
                f"/admin/finance/bank-movements/{refund['id']}", headers=accountant
            ).json()
            refund_sources = [candidate["source"] for candidate in refund_detail["candidates"]]
            assert refund_sources == ["sale_return"]
            refunded = client.post(
                f"/admin/finance/bank-movements/{refund['id']}/match",
                headers=accountant,
                json={"source": "sale_return", "source_id": str(ids["return_id"])},
            )
            assert refunded.status_code == 200
            assert refunded.json()["status"] == "reconciled"

            _import(
                client,
                accountant,
                account["id"],
                [
                    {
                        "occurred_on": "2026-10-25",
                        "amount_cents": -50000,
                        "reference": "RETIRO ANA LOPEZ",
                    }
                ],
            )
            outflow = client.get(
                "/admin/finance/bank-movements?search=RETIRO", headers=accountant
            ).json()["items"][0]
            invalid = client.post(
                f"/admin/finance/bank-movements/{outflow['id']}/match",
                headers=accountant,
                json={"source": "membership_payment", "source_id": str(ids["payment_id"])},
            )
            assert invalid.status_code == 422
            assert "retiro" in invalid.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_difference_note_flagging_and_manual_search() -> None:
    engine, ids = _prepare()
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            account = _create_account(client, accountant)
            _import(
                client,
                accountant,
                account["id"],
                [
                    {
                        "occurred_on": "2026-10-24",
                        "amount_cents": 50500,
                        "reference": "SPEI ANA LOPEZ",
                    }
                ],
            )
            movement = client.get(
                "/admin/finance/bank-movements", headers=accountant
            ).json()["items"][0]

            without_note = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/match",
                headers=accountant,
                json={"source": "membership_payment", "source_id": str(ids["payment_id"])},
            )
            assert without_note.status_code == 422
            assert "motivo de la diferencia" in without_note.json()["detail"]

            with_note = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/match",
                headers=accountant,
                json={
                    "source": "membership_payment",
                    "source_id": str(ids["payment_id"]),
                    "note": "Comisión bancaria descontada",
                },
            )
            assert with_note.status_code == 200
            difference = with_note.json()
            assert difference["status"] == "difference"
            assert difference["difference_cents"] == 500
            assert difference["note"] == "Comisión bancaria descontada"
            assert "diferencia de $5.00" in difference["events"][-1]["detail"]
            assert "$-" not in difference["events"][-1]["detail"]

            summary = client.get("/admin/finance/bank-movements", headers=accountant).json()["summary"]
            assert summary["difference"] == 1
            assert summary["difference_cents"] == 500

            flagged_match = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/flag",
                headers=accountant,
                json={"status": "reviewing", "note": "Revisar comisión"},
            )
            assert flagged_match.status_code == 409

            reopened = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/unmatch",
                headers=accountant,
                json={"reason": "Comisión por confirmar"},
            )
            assert reopened.status_code == 200
            assert "estado anterior: con diferencia" in reopened.json()["events"][-1]["detail"]

            no_note = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/flag",
                headers=accountant,
                json={"status": "difference"},
            )
            assert no_note.status_code == 422

            flagged = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/flag",
                headers=accountant,
                json={"status": "difference", "note": "Depósito sin identificar"},
            )
            assert flagged.status_code == 200
            assert flagged.json()["status"] == "difference"
            assert flagged.json()["matched_id"] is None

            summary = client.get("/admin/finance/bank-movements", headers=accountant).json()["summary"]
            assert summary["difference_cents"] == 50500

            back = client.post(
                f"/admin/finance/bank-movements/{movement['id']}/flag",
                headers=accountant,
                json={"status": "pending"},
            )
            assert back.status_code == 200
            assert back.json()["status"] == "pending"
            assert back.json()["note"] is None

            old_payment = datetime.now(timezone.utc) - timedelta(days=20)
            with Session(engine) as session:
                payment = session.get(Payment, ids["payment_id"])
                assert payment is not None
                payment.paid_at = old_payment
                session.add(payment)
                session.commit()

            current = client.get(
                f"/admin/finance/bank-movements/{movement['id']}", headers=accountant
            ).json()
            assert current["candidates"] == []
            searched = client.get(
                f"/admin/finance/bank-movements/{movement['id']}?candidate_search=Ana",
                headers=accountant,
            )
            assert searched.status_code == 200
            assert searched.json()["candidates"][0]["source_id"] == str(ids["payment_id"])
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
