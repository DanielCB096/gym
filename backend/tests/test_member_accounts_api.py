import re
from collections.abc import Iterator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member

FOLIO_PATTERN = re.compile(r"^V-\d{8}-[0-9A-F]{6}$")


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


def _seed_members(session: Session) -> tuple:
    member = Member(
        first_name="Ana", last_name="Lopez", email="ana@example.com", status="active"
    )
    other = Member(
        first_name="Beto", last_name="Ruiz", email="beto@example.com", status="active"
    )
    inactive = Member(first_name="Carla", last_name="Diaz", status="inactive")
    session.add_all([member, other, inactive])
    session.commit()
    return member.id, other.id, inactive.id


def _create_product(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/admin/products",
        headers=headers,
        json={
            "sku": "agua-600",
            "name": "Agua 600 ml",
            "category": "Bebidas",
            "price_cents": 1500,
            "initial_stock": 10,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_member_account_charge_payments_and_statement() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _, inactive_id = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            product_id = _create_product(client, manager)

            charge = {
                "items": [{"product_id": product_id, "quantity": 2}],
                "payment_method": "account",
                "member_id": str(member_id),
            }

            # The account is part of the register operation: it needs a shift.
            assert client.post("/admin/sales", headers=reception, json=charge).status_code == 409

            opened = client.post(
                "/admin/cash-sessions", headers=reception, json={"opening_cash_cents": 10000}
            )
            assert opened.status_code == 201, opened.text
            cash_session_id = opened.json()["id"]

            # Charging to an account requires an identifiable, active member.
            assert client.post(
                "/admin/sales",
                headers=reception,
                json={**charge, "member_id": None},
            ).status_code == 422
            assert client.post(
                "/admin/sales",
                headers=reception,
                json={**charge, "member_id": str(inactive_id)},
            ).status_code == 404

            sale = client.post("/admin/sales", headers=reception, json=charge)
            assert sale.status_code == 201, sale.text
            sale_body = sale.json()
            assert FOLIO_PATTERN.match(sale_body["folio"]), sale_body["folio"]
            assert sale_body["payment_method"] == "account"
            assert sale_body["total_cents"] == 3000
            assert sale_body["cash_session_id"] == cash_session_id

            # An account sale is revenue but no money entered the register.
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["account_sales_cents"] == 3000
            assert current["cash_sales_cents"] == 0
            assert current["total_sales_cents"] == 3000
            assert current["expected_cash_cents"] == 10000
            assert current["account_payments_cents"] == 0

            directory = client.get("/admin/member-accounts", headers=reception).json()
            assert directory["members_with_balance"] == 1
            assert directory["total_receivable_cents"] == 3000
            assert directory["total_credit_cents"] == 0
            assert directory["items"][0]["member_id"] == str(member_id)
            assert directory["items"][0]["balance_cents"] == 3000
            assert directory["items"][0]["charges_count"] == 1
            assert directory["items"][0]["oldest_charge_at"] is not None

            statement = client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            ).json()
            assert statement["summary"]["charges_cents"] == 3000
            assert statement["summary"]["payments_cents"] == 0
            assert statement["summary"]["balance_cents"] == 3000
            assert len(statement["entries"]) == 1
            assert statement["entries"][0]["kind"] == "charge"
            assert statement["entries"][0]["amount_cents"] == 3000
            assert statement["entries"][0]["balance_cents"] == 3000
            assert statement["entries"][0]["reference"] == sale_body["folio"]

            # Overpaying is rejected: a payment cannot create a credit.
            assert client.post(
                f"/admin/member-accounts/{member_id}/payments",
                headers=reception,
                json={"amount_cents": 3001, "method": "cash"},
            ).status_code == 409

            first_payment = client.post(
                f"/admin/member-accounts/{member_id}/payments",
                headers=reception,
                json={"amount_cents": 1000, "method": "cash", "note": "Abono"},
            )
            assert first_payment.status_code == 201, first_payment.text
            assert first_payment.json()["balance_cents"] == 2000
            assert first_payment.json()["cash_session_id"] == cash_session_id
            assert first_payment.json()["actor_email"] == "reception@example.com"

            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["account_payments_count"] == 1
            assert current["account_payments_cents"] == 1000
            assert current["cash_account_payments_cents"] == 1000
            assert current["expected_cash_cents"] == 11000

            # A card payment clears the balance but does not touch the cash drawer.
            second_payment = client.post(
                f"/admin/member-accounts/{member_id}/payments",
                headers=reception,
                json={"amount_cents": 2000, "method": "card"},
            )
            assert second_payment.status_code == 201, second_payment.text
            assert second_payment.json()["balance_cents"] == 0
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["account_payments_cents"] == 3000
            assert current["expected_cash_cents"] == 11000

            # Nothing left to collect.
            assert client.post(
                f"/admin/member-accounts/{member_id}/payments",
                headers=reception,
                json={"amount_cents": 100, "method": "cash"},
            ).status_code == 409
            directory = client.get("/admin/member-accounts", headers=reception).json()
            assert directory["items"] == []
            assert directory["total_receivable_cents"] == 0

            # The statement keeps the whole history, newest first, with the running
            # balance after each entry.
            statement = client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            ).json()
            assert statement["summary"]["balance_cents"] == 0
            assert [entry["kind"] for entry in statement["entries"]] == [
                "payment",
                "payment",
                "charge",
            ]
            assert statement["entries"][0]["balance_cents"] == 0
            assert statement["entries"][1]["balance_cents"] == 2000
            assert statement["entries"][2]["balance_cents"] == 3000

            # The sale directory exposes the account tender.
            listed = client.get(
                "/admin/sales", headers=reception, params={"payment_method": "account"}
            ).json()
            assert listed["total"] == 1
            assert listed["summary"]["account_cents"] == 3000
            assert listed["summary"]["cash_cents"] == 0

            # Reading balances is part of the register; collecting is a register
            # operation. The accountant may audit but not move money.
            assert client.get("/admin/member-accounts", headers=trainer).status_code == 403
            assert client.get("/admin/member-accounts", headers=accountant).status_code == 200
            assert client.post(
                f"/admin/member-accounts/{member_id}/payments",
                headers=accountant,
                json={"amount_cents": 100, "method": "cash"},
            ).status_code == 403
            assert client.get(f"/admin/member-accounts/{uuid4()}", headers=reception).status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_account_sale_returns_credit_the_account_instead_of_cash() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _, _ = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            product_id = _create_product(client, manager)
            client.post(
                "/admin/cash-sessions", headers=reception, json={"opening_cash_cents": 5000}
            )

            sale = client.post(
                "/admin/sales",
                headers=reception,
                json={
                    "items": [{"product_id": product_id, "quantity": 2}],
                    "payment_method": "account",
                    "member_id": str(member_id),
                },
            )
            assert sale.status_code == 201, sale.text
            sale_body = sale.json()
            sale_item_id = sale_body["lines"][0]["sale_item_id"]

            return_line = {"sale_item_id": sale_item_id, "quantity": 1, "disposition": "restock"}

            # Money was never collected, so it cannot be refunded in cash.
            assert client.post(
                f"/admin/sales/{sale_body['id']}/returns",
                headers=reception,
                json={
                    "items": [return_line],
                    "refund_method": "cash",
                    "reason": "Talla equivocada",
                },
            ).status_code == 422

            partial = client.post(
                f"/admin/sales/{sale_body['id']}/returns",
                headers=reception,
                json={
                    "items": [return_line],
                    "refund_method": "account",
                    "reason": "Talla equivocada",
                },
            )
            assert partial.status_code == 201, partial.text
            assert partial.json()["refund_method"] == "account"
            assert partial.json()["total_refund_cents"] == 1500

            statement = client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            ).json()
            assert statement["summary"]["charges_cents"] == 3000
            assert statement["summary"]["credits_cents"] == 1500
            assert statement["summary"]["balance_cents"] == 1500
            assert [entry["kind"] for entry in statement["entries"]] == ["credit", "charge"]
            assert statement["entries"][0]["amount_cents"] == -1500
            assert statement["entries"][0]["balance_cents"] == 1500

            # The credit did not move the cash drawer.
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["account_refunds_cents"] == 1500
            assert current["cash_refunds_cents"] == 0
            assert current["expected_cash_cents"] == 5000

            # The rest of the sale can be returned without specifying the method:
            # an account sale always credits the account.
            remaining = client.post(
                f"/admin/sales/{sale_body['id']}/returns",
                headers=reception,
                json={
                    "items": [return_line],
                    "reason": "Segunda devolución",
                },
            )
            assert remaining.status_code == 201, remaining.text
            assert remaining.json()["refund_method"] == "account"
            statement = client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            ).json()
            assert statement["summary"]["balance_cents"] == 0

            # A cash sale cannot be "refunded" into an account: that would erase
            # money the club actually collected.
            cash_sale = client.post(
                "/admin/sales",
                headers=reception,
                json={
                    "items": [{"product_id": product_id, "quantity": 1}],
                    "payment_method": "cash",
                },
            )
            assert cash_sale.status_code == 201, cash_sale.text
            cash_item_id = cash_sale.json()["lines"][0]["sale_item_id"]
            assert client.post(
                f"/admin/sales/{cash_sale.json()['id']}/returns",
                headers=reception,
                json={
                    "items": [
                        {"sale_item_id": cash_item_id, "quantity": 1, "disposition": "restock"}
                    ],
                    "refund_method": "account",
                    "reason": "No aplica",
                },
            ).status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
