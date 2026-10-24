import re
from collections.abc import Iterator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import InventoryMovement, SaleReturn, SaleReturnItem
from app.modules.memberships.models import Member

RETURN_FOLIO_PATTERN = re.compile(r"^D-\d{8}-[0-9A-F]{6}$")


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
    register_user(
        session,
        email="manager@example.com",
        password="manager-strong-password",
        role_codes=("manager",),
    )
    register_user(
        session,
        email="reception@example.com",
        password="reception-strong-password",
        role_codes=("reception",),
    )
    register_user(
        session,
        email="accountant@example.com",
        password="accountant-strong-password",
        role_codes=("accountant",),
    )
    register_user(
        session,
        email="trainer@example.com",
        password="trainer-strong-password",
        role_codes=("trainer",),
    )


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _open_shift(client: TestClient, headers: dict[str, str], opening: int = 0) -> str:
    response = client.post("/admin/cash-sessions", headers=headers, json={"opening_cash_cents": opening})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_sale_return_restock_and_partial_then_full() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member = Member(first_name="Ana", last_name="Lopez", email="ana@example.com")
        session.add(member)
        session.commit()
        member_id = member.id

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")

            product = client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "proteina", "name": "Proteína", "price_cents": 5000, "initial_stock": 10},
            ).json()
            product_id = product["id"]

            shift_id = _open_shift(client, reception, 0)

            sale = client.post(
                "/admin/sales",
                headers=reception,
                json={
                    "items": [{"product_id": product_id, "quantity": 3}],
                    "payment_method": "cash",
                    "member_id": str(member_id),
                },
            ).json()
            assert sale["total_cents"] == 15000
            assert sale["refunded_cents"] == 0
            line = sale["lines"][0]
            assert line["returnable_quantity"] == 3
            assert line["refunded_quantity"] == 0
            sale_item_id = line["sale_item_id"]
            assert sale_item_id

            assert client.get("/admin/products", headers=reception, params={"search": "proteina"}).json()["items"][0]["stock"] == 7

            # Partial restock return: two of the three units go back to stock.
            partial = client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={
                    "items": [{"sale_item_id": sale_item_id, "quantity": 2, "disposition": "restock"}],
                    "refund_method": "cash",
                    "reason": "Producto en buen estado",
                },
            )
            assert partial.status_code == 201, partial.text
            partial_body = partial.json()
            assert RETURN_FOLIO_PATTERN.match(partial_body["folio"]), partial_body["folio"]
            assert partial_body["sale_folio"] == sale["folio"]
            assert partial_body["total_refund_cents"] == 10000
            assert partial_body["refund_method"] == "cash"
            assert partial_body["cash_session_id"] == shift_id
            assert partial_body["actor_email"] == "reception@example.com"
            assert partial_body["member_name"] == "Ana Lopez"
            assert partial_body["reason"] == "Producto en buen estado"
            assert partial_body["lines"][0]["disposition"] == "restock"
            assert partial_body["lines"][0]["line_refund_cents"] == 10000

            assert client.get("/admin/products", headers=reception, params={"search": "proteina"}).json()["items"][0]["stock"] == 9

            # The sale is partially refunded: still completed, with a refund total.
            listed = client.get("/admin/sales", headers=reception, params={"search": sale["folio"]}).json()
            returned_sale = listed["items"][0]
            assert returned_sale["status"] == "completed"
            assert returned_sale["refunded_cents"] == 10000
            assert returned_sale["lines"][0]["refunded_quantity"] == 2
            assert returned_sale["lines"][0]["returnable_quantity"] == 1
            assert listed["summary"]["refunds_cents"] == 10000
            assert listed["summary"]["refunded_count"] == 1

            # Returns are listed and can be filtered by sale.
            directory = client.get("/admin/sales/returns", headers=reception).json()
            assert directory["total"] == 1
            assert directory["summary"] == {
                "count": 1,
                "total_refund_cents": 10000,
                "cash_refund_cents": 10000,
                "card_refund_cents": 0,
                "transfer_refund_cents": 0,
                "account_refund_cents": 0,
            }
            by_sale = client.get("/admin/sales/returns", headers=reception, params={"sale_id": sale["id"]}).json()
            assert by_sale["total"] == 1
            assert client.get("/admin/sales/returns", headers=reception, params={"sale_id": str(uuid4())}).json()["total"] == 0
            by_search = client.get("/admin/sales/returns", headers=reception, params={"search": partial_body["folio"]}).json()
            assert by_search["total"] == 1

            # Returning the last unit flips the sale to a full refund.
            final = client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={
                    "items": [{"sale_item_id": sale_item_id, "quantity": 1}],
                    "reason": "Cliente cancela la compra",
                },
            )
            assert final.status_code == 201, final.text
            assert final.json()["refund_method"] == "cash"  # defaults to the sale's method

            after = client.get("/admin/sales", headers=reception, params={"search": sale["folio"]}).json()["items"][0]
            assert after["status"] == "refunded"
            assert after["refunded_cents"] == 15000
            assert after["lines"][0]["returnable_quantity"] == 0

        with Session(engine) as session:
            movements = session.exec(
                select(InventoryMovement).order_by(InventoryMovement.occurred_at, InventoryMovement.id)
            ).all()
            assert [movement.movement_type for movement in movements] == ["intake", "sale", "return", "return"]
            assert [movement.quantity for movement in movements] == [10, -3, 2, 1]
            assert movements[-1].reference_type == "sale_return"
            returns = session.exec(select(SaleReturn)).all()
            assert len(returns) == 2
            assert sum(item.quantity for item in session.exec(select(SaleReturnItem)).all()) == 3
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_sale_return_write_off_and_validation() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")

            first = client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "shaker", "name": "Shaker", "price_cents": 2000, "initial_stock": 5},
            ).json()
            second = client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "toalla", "name": "Toalla", "price_cents": 1500, "initial_stock": 5},
            ).json()
            _open_shift(client, reception)

            sale = client.post(
                "/admin/sales",
                headers=reception,
                json={"items": [{"product_id": first["id"], "quantity": 4}], "payment_method": "card"},
            ).json()
            line_id = sale["lines"][0]["sale_item_id"]

            other_sale = client.post(
                "/admin/sales",
                headers=reception,
                json={"items": [{"product_id": second["id"], "quantity": 1}], "payment_method": "cash"},
            ).json()
            other_line_id = other_sale["lines"][0]["sale_item_id"]

            # A write-off receives the goods and discards them: net stock is unchanged.
            write_off = client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={
                    "items": [{"sale_item_id": line_id, "quantity": 2, "disposition": "write_off"}],
                    "reason": "Producto dañado",
                },
            )
            assert write_off.status_code == 201, write_off.text
            assert write_off.json()["lines"][0]["disposition"] == "write_off"
            assert client.get("/admin/products", headers=reception, params={"search": "shaker"}).json()["items"][0]["stock"] == 1

            # Over-returning the remaining two units is a conflict.
            assert client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={"items": [{"sale_item_id": line_id, "quantity": 3}], "reason": "De más"},
            ).status_code == 409

            # Validation guards.
            assert client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={"items": [{"sale_item_id": line_id, "quantity": 1}], "reason": "   "},
            ).status_code == 422
            assert client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={"items": [{"sale_item_id": line_id, "quantity": 0}], "reason": "Cero"},
            ).status_code == 422
            assert client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={"items": [{"sale_item_id": line_id, "quantity": 1, "disposition": "regalar"}], "reason": "Mala"},
            ).status_code == 422
            assert client.post(
                f"/admin/sales/{uuid4()}/returns",
                headers=reception,
                json={"items": [{"sale_item_id": line_id, "quantity": 1}], "reason": "Venta inexistente"},
            ).status_code == 404

            # A line from another sale cannot be returned against this one.
            assert client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={"items": [{"sale_item_id": other_line_id, "quantity": 1}], "reason": "Línea ajena"},
            ).status_code == 404

        with Session(engine) as session:
            movements = session.exec(
                select(InventoryMovement).order_by(InventoryMovement.occurred_at, InventoryMovement.id)
            ).all()
            kinds = [movement.movement_type for movement in movements]
            # intake x2, both sales, then the write-off's return + waste. The
            # return and its waste share the same timestamp, so compare as a set.
            assert sorted(kinds) == ["intake", "intake", "return", "sale", "sale", "waste"]
            write_off_movements = sorted(
                (movement.movement_type, movement.quantity)
                for movement in movements
                if movement.reference_type == "sale_return"
            )
            assert write_off_movements == [("return", 2), ("waste", -2)]
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_sale_return_cash_session_and_permissions() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")

            product = client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "agua", "name": "Agua", "price_cents": 2000, "initial_stock": 10},
            ).json()

            shift_id = _open_shift(client, reception, 10000)
            sale = client.post(
                "/admin/sales",
                headers=reception,
                json={"items": [{"product_id": product["id"], "quantity": 2}], "payment_method": "cash"},
            ).json()
            assert client.get("/admin/cash-sessions/current", headers=reception).json()["expected_cash_cents"] == 14000

            # A cash refund lowers the expected cash of the shift at close.
            returned = client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={
                    "items": [{"sale_item_id": sale["lines"][0]["sale_item_id"], "quantity": 1}],
                    "refund_method": "cash",
                    "reason": "Cambio",
                },
            )
            assert returned.status_code == 201, returned.text
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["refunds_count"] == 1
            assert current["total_refunds_cents"] == 2000
            assert current["cash_refunds_cents"] == 2000
            assert current["expected_cash_cents"] == 12000

            closed = client.post(
                f"/admin/cash-sessions/{shift_id}/close",
                headers=reception,
                json={"counted_cash_cents": 12000},
            )
            assert closed.status_code == 200, closed.text
            assert closed.json()["expected_cash_cents"] == 12000
            assert closed.json()["difference_cents"] == 0

            # The register must be open to refund; a fresh shift is required.
            assert client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=reception,
                json={"items": [{"sale_item_id": sale["lines"][0]["sale_item_id"], "quantity": 1}], "reason": "Sin turno"},
            ).status_code == 409

            # Permissions: accountants read returns, trainers cannot, and the
            # register is written only with sales.manage.
            assert client.get("/admin/sales/returns", headers=accountant).status_code == 200
            assert client.get("/admin/sales/returns", headers=trainer).status_code == 403
            assert client.get("/admin/sales/returns").status_code == 401
            assert client.post(
                f"/admin/sales/{sale['id']}/returns",
                headers=accountant,
                json={"items": [{"sale_item_id": sale["lines"][0]["sale_item_id"], "quantity": 1}], "reason": "No puede"},
            ).status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
