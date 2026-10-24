import re
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import InventoryMovement
from app.modules.inventory.service import (
    create_product,
    create_purchase_order,
    create_supplier,
    open_cash_session,
    register_sale,
    register_sale_return,
)
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


def test_products_catalog_permissions_and_filters() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            assert client.get("/admin/products").status_code == 401
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")

            created = client.post(
                "/admin/products",
                headers=manager,
                json={
                    "sku": "agua-600",
                    "name": "Agua 600 ml",
                    "category": "Bebidas",
                    "barcode": "7501234567890",
                    "price_cents": 1500,
                    "cost_cents": 700,
                    "stock_min": 3,
                },
            )
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["sku"] == "agua-600"
            assert body["category"] == "Bebidas"
            assert body["stock"] == 0
            assert body["state"] == "out"
            product_id = body["id"]

            # SKUs are unique case-insensitively and so are barcodes.
            assert client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "AGUA-600", "name": "Otra", "price_cents": 100},
            ).status_code == 409
            assert client.post(
                "/admin/products",
                headers=manager,
                json={
                    "sku": "otra",
                    "name": "Otra",
                    "price_cents": 100,
                    "barcode": "7501234567890",
                },
            ).status_code == 409
            # A barcode alone stays optional and can be omitted.
            assert client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "sin-codigo", "name": "Sin código", "price_cents": 100},
            ).status_code == 201

            stocked = client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "barra", "name": "Barra proteína", "price_cents": 4500, "initial_stock": 10, "stock_min": 3},
            )
            assert stocked.status_code == 201, stocked.text
            assert stocked.json()["state"] == "active"

            directory = client.get("/admin/products", headers=reception)
            assert directory.status_code == 200, directory.text
            data = directory.json()
            assert data["total"] == 3
            assert data["summary"] == {"total": 3, "active": 1, "low_stock": 0, "out_of_stock": 2, "inactive": 0}
            assert data["categories"] == ["Bebidas", "General"]

            searched = client.get("/admin/products", headers=reception, params={"search": "agua"}).json()
            assert searched["total"] == 1
            assert searched["items"][0]["sku"] == "agua-600"

            by_category = client.get("/admin/products", headers=reception, params={"category": "Bebidas"}).json()
            assert by_category["total"] == 1
            # Summary stays club-wide while filtering.
            assert by_category["summary"]["out_of_stock"] == 2
            assert client.get("/admin/products", headers=reception, params={"state": "out"}).json()["total"] == 2
            assert client.get("/admin/products", headers=reception, params={"state": "active"}).json()["total"] == 1
            assert client.get("/admin/products", headers=reception, params={"state": "bogus"}).status_code == 422

            updated = client.patch(
                f"/admin/products/{product_id}",
                headers=manager,
                json={
                    "name": "Agua 600 ml fría",
                    "category": "Bebidas",
                    "price_cents": 1800,
                    "cost_cents": 700,
                    "stock_min": 5,
                    "is_active": True,
                },
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["name"] == "Agua 600 ml fría"
            assert updated.json()["price_cents"] == 1800
            assert client.patch(
                f"/admin/products/{uuid4()}",
                headers=manager,
                json={"name": "Nadie", "price_cents": 100},
            ).status_code == 404
            assert client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "malo", "name": "Malo", "price_cents": -1},
            ).status_code == 422

            # Reception sells but does not manage the catalog.
            assert client.post(
                "/admin/products",
                headers=reception,
                json={"sku": "nope", "name": "Nope", "price_cents": 100},
            ).status_code == 403
            assert client.patch(
                f"/admin/products/{product_id}",
                headers=reception,
                json={"name": "Nope", "price_cents": 100},
            ).status_code == 403

            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            assert client.get("/admin/products", headers=accountant).status_code == 403
            assert client.post(
                "/admin/products",
                headers=accountant,
                json={"sku": "x", "name": "x", "price_cents": 1},
            ).status_code == 403

            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            assert client.get("/admin/products", headers=trainer).status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_product_stock_movements_and_ledger() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            created = client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "proteina", "name": "Proteína", "price_cents": 5000, "initial_stock": 10},
            ).json()
            product_id = created["id"]
            assert created["stock"] == 10

            intake = client.post(
                f"/admin/products/{product_id}/stock",
                headers=manager,
                json={"movement_type": "intake", "quantity": 5},
            )
            assert intake.status_code == 200, intake.text
            assert intake.json()["stock"] == 15

            waste = client.post(
                f"/admin/products/{product_id}/stock",
                headers=manager,
                json={"movement_type": "waste", "quantity": 3, "reason": "Caducado"},
            )
            assert waste.status_code == 200, waste.text
            assert waste.json()["stock"] == 12

            # Waste and adjustments need a reason.
            assert client.post(
                f"/admin/products/{product_id}/stock",
                headers=manager,
                json={"movement_type": "waste", "quantity": 1},
            ).status_code == 422
            assert client.post(
                f"/admin/products/{product_id}/stock",
                headers=manager,
                json={"movement_type": "adjustment", "quantity": -1},
            ).status_code == 422
            # Waste cannot take more than the available stock.
            assert client.post(
                f"/admin/products/{product_id}/stock",
                headers=manager,
                json={"movement_type": "waste", "quantity": 100, "reason": "Roto"},
            ).status_code == 409
            # A negative waste quantity is a client error, not a silent side effect.
            assert client.post(
                f"/admin/products/{product_id}/stock",
                headers=manager,
                json={"movement_type": "waste", "quantity": -1, "reason": "Roto"},
            ).status_code == 422
            # Adjustments may be negative and explanation is mandatory.
            adjusted = client.post(
                f"/admin/products/{product_id}/stock",
                headers=manager,
                json={"movement_type": "adjustment", "quantity": -2, "reason": "Conteo físico"},
            )
            assert adjusted.status_code == 200, adjusted.text
            assert adjusted.json()["stock"] == 10
            assert client.post(
                f"/admin/products/{product_id}/stock",
                headers=manager,
                json={"movement_type": "adjustment", "quantity": -100, "reason": "Conteo"},
            ).status_code == 409
            assert client.post(
                f"/admin/products/{uuid4()}/stock",
                headers=manager,
                json={"movement_type": "intake", "quantity": 1},
            ).status_code == 404

            # Reception may consult stock but not adjust it.
            reception = _login(client, "reception@example.com", "reception-strong-password")
            assert client.post(
                f"/admin/products/{product_id}/stock",
                headers=reception,
                json={"movement_type": "intake", "quantity": 1},
            ).status_code == 403

        with Session(engine) as session:
            movements = session.exec(
                select(InventoryMovement).order_by(InventoryMovement.occurred_at, InventoryMovement.id)
            ).all()
            kinds = [movement.movement_type for movement in movements]
            assert kinds == ["intake", "intake", "waste", "adjustment"]
            assert [movement.quantity for movement in movements] == [10, 5, -3, -2]
            assert movements[-1].reason == "Conteo físico"
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_cash_session_and_sales_flow() -> None:
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
            headers = _login(client, "reception@example.com", "reception-strong-password")

            # No open shift yet.
            assert client.get("/admin/cash-sessions/current", headers=headers).json() is None
            assert client.post(
                "/admin/products",
                headers=manager,
                json={"sku": "agua", "name": "Agua", "price_cents": 1500, "initial_stock": 5},
            ).status_code == 201
            sale_product = client.get("/admin/products", headers=headers, params={"search": "agua"}).json()["items"][0]
            product_id = sale_product["id"]

            # Sales require an open register shift.
            early = client.post(
                "/admin/sales",
                headers=headers,
                json={"items": [{"product_id": product_id, "quantity": 1}], "payment_method": "cash"},
            )
            assert early.status_code == 409

            opened = client.post("/admin/cash-sessions", headers=headers, json={"opening_cash_cents": 20000})
            assert opened.status_code == 201, opened.text
            cash_session = opened.json()
            assert cash_session["status"] == "open"
            assert cash_session["opening_cash_cents"] == 20000
            assert cash_session["opened_by_email"] == "reception@example.com"
            # Only one shift may be open at a time.
            assert client.post("/admin/cash-sessions", headers=headers, json={"opening_cash_cents": 0}).status_code == 409

            sale = client.post(
                "/admin/sales",
                headers=headers,
                json={
                    "items": [{"product_id": product_id, "quantity": 2}],
                    "payment_method": "cash",
                    "member_id": str(member_id),
                },
            )
            assert sale.status_code == 201, sale.text
            sale_body = sale.json()
            assert FOLIO_PATTERN.match(sale_body["folio"]), sale_body["folio"]
            assert sale_body["total_cents"] == 3000
            assert sale_body["subtotal_cents"] == 3000
            assert sale_body["cash_session_id"] == cash_session["id"]
            assert sale_body["member_name"] == "Ana Lopez"
            assert sale_body["cashier_email"] == "reception@example.com"
            assert sale_body["lines"][0]["quantity"] == 2
            assert sale_body["lines"][0]["line_total_cents"] == 3000

            # The sale moved stock through the ledger.
            assert client.get("/admin/products", headers=headers, params={"search": "agua"}).json()["items"][0]["stock"] == 3

            # A card sale does not change the expected cash.
            assert client.post(
                "/admin/sales",
                headers=headers,
                json={"items": [{"product_id": product_id, "quantity": 1}], "payment_method": "card"},
            ).status_code == 201

            current = client.get("/admin/cash-sessions/current", headers=headers).json()
            assert current["sales_count"] == 2
            assert current["total_sales_cents"] == 4500
            assert current["cash_sales_cents"] == 3000
            assert current["card_sales_cents"] == 1500
            assert current["expected_cash_cents"] == 23000

            # Guards: insufficient stock, unknown members, malformed carts.
            assert client.post(
                "/admin/sales",
                headers=headers,
                json={"items": [{"product_id": product_id, "quantity": 99}], "payment_method": "cash"},
            ).status_code == 409
            assert client.post(
                "/admin/sales",
                headers=headers,
                json={"items": [{"product_id": product_id, "quantity": 1}], "payment_method": "cash", "member_id": str(uuid4())},
            ).status_code == 404
            assert client.post(
                "/admin/sales",
                headers=headers,
                json={
                    "items": [
                        {"product_id": product_id, "quantity": 1},
                        {"product_id": product_id, "quantity": 1},
                    ],
                    "payment_method": "cash",
                },
            ).status_code == 422
            assert client.post("/admin/sales", headers=headers, json={"items": [], "payment_method": "cash"}).status_code == 422
            assert client.post(
                "/admin/sales",
                headers=headers,
                json={"items": [{"product_id": product_id, "quantity": 1}], "payment_method": "bitcoin"},
            ).status_code == 422

            # Deactivating a product blocks selling it (manager only).
            inventory = client.get("/admin/products", headers=headers, params={"search": "agua"}).json()["items"][0]
            assert client.patch(
                f"/admin/products/{product_id}",
                headers=manager,
                json={
                    "name": inventory["name"],
                    "category": inventory["category"],
                    "price_cents": inventory["price_cents"],
                    "stock_min": inventory["stock_min"],
                    "is_active": False,
                },
            ).status_code == 200
            assert client.post(
                "/admin/sales",
                headers=headers,
                json={"items": [{"product_id": product_id, "quantity": 1}], "payment_method": "cash"},
            ).status_code == 409

            # Listing and filtering sales.
            listed = client.get("/admin/sales", headers=headers)
            assert listed.status_code == 200, listed.text
            assert listed.json()["total"] == 2
            assert listed.json()["summary"] == {
                "count": 2,
                "total_cents": 4500,
                "cash_cents": 3000,
                "card_cents": 1500,
                "transfer_cents": 0,
                "account_cents": 0,
                "refunds_cents": 0,
                "refunded_count": 0,
            }
            cash_only = client.get("/admin/sales", headers=headers, params={"payment_method": "cash"}).json()
            assert cash_only["total"] == 1
            assert cash_only["summary"]["total_cents"] == 4500
            by_search = client.get("/admin/sales", headers=headers, params={"search": "lopez"}).json()
            assert by_search["total"] == 1

            # Closing requires an explanation when the counted cash differs.
            close_url = f"/admin/cash-sessions/{cash_session['id']}/close"
            assert client.post(close_url, headers=headers, json={"counted_cash_cents": 10000}).status_code == 422
            closed = client.post(
                close_url,
                headers=headers,
                json={"counted_cash_cents": 22500, "notes": "Faltante de 50 por cambio mal dado"},
            )
            assert closed.status_code == 200, closed.text
            assert closed.json()["status"] == "closed"
            assert closed.json()["expected_cash_cents"] == 23000
            assert closed.json()["difference_cents"] == -500
            assert closed.json()["closed_by_email"] == "reception@example.com"
            # A closed shift stays closed and a new one may open.
            assert client.post(close_url, headers=headers, json={"counted_cash_cents": 23000}).status_code == 409
            assert client.get("/admin/cash-sessions/current", headers=headers).json() is None
            assert client.post(close_url, headers=headers, json={"counted_cash_cents": 1}).status_code == 409

            history = client.get("/admin/cash-sessions", headers=headers).json()
            assert len(history) == 1
            assert history[0]["status"] == "closed"

            # Accountants can read sales but never operate the register.
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            assert client.get("/admin/sales", headers=accountant).status_code == 200
            assert client.get("/admin/cash-sessions", headers=accountant).status_code == 200
            assert client.post(
                "/admin/cash-sessions",
                headers=accountant,
                json={"opening_cash_cents": 0},
            ).status_code == 403
            assert client.post(
                "/admin/sales",
                headers=accountant,
                json={"items": [{"product_id": product_id, "quantity": 1}], "payment_method": "cash"},
            ).status_code == 403
            assert client.get("/admin/sales").status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_folios_carry_the_club_calendar_day() -> None:
    """The date in a folio is the club's local day, not the UTC day.

    Mexico is UTC-6, so a sale rung up at 20:00 local is already the next day in
    UTC. The folio must still read the local day the operator sees.
    """

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        product = create_product(
            session, sku="agua", name="Agua", price_cents=1500, initial_stock=10
        )
        open_cash_session(session, opening_cash_cents=0)

        # 2026-10-19 02:00 UTC == 2026-10-18 20:00 in Mexico.
        evening = register_sale(
            session,
            items=[(product.id, 1)],
            payment_method="cash",
            now=datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc),
        )
        assert evening.folio.startswith("V-20261018-"), evening.folio
        # The stored instant stays in UTC; only the folio label is local.
        assert evening.sold_at == datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)

        refund = register_sale_return(
            session,
            evening.id,
            lines=[(evening.lines[0].sale_item_id, 1, "restock")],
            reason="Cambio de opinión",
            now=datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc),
        )
        assert refund.folio.startswith("D-20261018-"), refund.folio

        # Purchase orders carry the same club-local day in their ``OC-…`` folio.
        supplier = create_supplier(session, name="Proveedor")
        order = create_purchase_order(
            session,
            supplier_id=supplier.id,
            lines=[(product.id, 1, 1000)],
            now=datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc),
        )
        assert order.folio.startswith("OC-20261018-"), order.folio
    engine.dispose()


def test_suppliers_and_purchase_orders_flow() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")

            # Suppliers: create, unique name (case-insensitive) and permissions.
            created = client.post(
                "/admin/suppliers",
                headers=manager,
                json={
                    "name": "Distribuidora Norte",
                    "contact_name": "Ana",
                    "phone": "555-0100",
                    "email": "ana@norte.mx",
                },
            )
            assert created.status_code == 201, created.text
            supplier = created.json()
            supplier_id = supplier["id"]
            assert supplier["is_active"] is True
            assert client.post(
                "/admin/suppliers", headers=manager, json={"name": "distribuidora norte"}
            ).status_code == 409
            assert client.post(
                "/admin/suppliers", headers=reception, json={"name": "Otro proveedor"}
            ).status_code == 403
            assert client.get("/admin/suppliers", headers=reception).json()["total"] == 1

            renamed = client.patch(
                f"/admin/suppliers/{supplier_id}",
                headers=manager,
                json={"name": "Distribuidora Norte SA", "is_active": True},
            )
            assert renamed.status_code == 200, renamed.text
            assert renamed.json()["name"] == "Distribuidora Norte SA"

            # A product to restock.
            product = client.post(
                "/admin/products",
                headers=manager,
                json={
                    "sku": "proteina-1kg",
                    "name": "Proteína 1 kg",
                    "category": "Suplementos",
                    "price_cents": 90000,
                    "cost_cents": 50000,
                    "stock_min": 5,
                    "initial_stock": 2,
                },
            ).json()
            product_id = product["id"]
            assert product["stock"] == 2

            # Create the purchase order.
            order = client.post(
                "/admin/purchase-orders",
                headers=manager,
                json={
                    "supplier_id": supplier_id,
                    "items": [{"product_id": product_id, "quantity": 10, "unit_cost_cents": 45000}],
                    "expected_at": "2026-10-25",
                    "notes": "Reposición de octubre",
                },
            )
            assert order.status_code == 201, order.text
            body = order.json()
            assert re.match(r"^OC-\d{8}-[0-9A-F]{6}$", body["folio"]), body["folio"]
            assert body["status"] == "created"
            assert body["subtotal_cents"] == 450000
            assert body["total_cents"] == 450000
            assert body["expected_at"] == "2026-10-25"
            assert body["created_by_email"] == "manager@example.com"
            line = body["lines"][0]
            assert line["quantity"] == 10
            assert line["received_quantity"] == 0
            assert line["pending_quantity"] == 10
            order_id = body["id"]
            item_id = line["item_id"]

            # Validation: empty cart, unknown supplier, unknown product, duplicate line.
            assert client.post(
                "/admin/purchase-orders",
                headers=manager,
                json={"supplier_id": supplier_id, "items": []},
            ).status_code == 422
            assert client.post(
                "/admin/purchase-orders",
                headers=manager,
                json={
                    "supplier_id": str(uuid4()),
                    "items": [{"product_id": product_id, "quantity": 1, "unit_cost_cents": 1}],
                },
            ).status_code == 404
            assert client.post(
                "/admin/purchase-orders",
                headers=manager,
                json={
                    "supplier_id": supplier_id,
                    "items": [{"product_id": str(uuid4()), "quantity": 1, "unit_cost_cents": 1}],
                },
            ).status_code == 404
            assert client.post(
                "/admin/purchase-orders",
                headers=manager,
                json={
                    "supplier_id": supplier_id,
                    "items": [
                        {"product_id": product_id, "quantity": 1, "unit_cost_cents": 1},
                        {"product_id": product_id, "quantity": 2, "unit_cost_cents": 1},
                    ],
                },
            ).status_code == 422
            # Reception may read orders but not manage them.
            assert client.post(
                "/admin/purchase-orders",
                headers=reception,
                json={
                    "supplier_id": supplier_id,
                    "items": [{"product_id": product_id, "quantity": 1, "unit_cost_cents": 1}],
                },
            ).status_code == 403

            # Send it; a second send is a state conflict.
            sent = client.post(f"/admin/purchase-orders/{order_id}/send", headers=manager)
            assert sent.status_code == 200, sent.text
            assert sent.json()["status"] == "sent"
            assert sent.json()["sent_at"] is not None
            assert (
                client.post(f"/admin/purchase-orders/{order_id}/send", headers=manager).status_code
                == 409
            )

            # Partial receive: stock and replacement cost move, order stays open.
            partial = client.post(
                f"/admin/purchase-orders/{order_id}/receive",
                headers=manager,
                json={"items": [{"item_id": item_id, "quantity": 6}]},
            )
            assert partial.status_code == 200, partial.text
            partial_body = partial.json()
            assert partial_body["status"] == "sent"
            assert partial_body["lines"][0]["received_quantity"] == 6
            assert partial_body["lines"][0]["pending_quantity"] == 4
            product_after = client.get(
                "/admin/products", headers=manager, params={"search": "proteina"}
            ).json()["items"][0]
            assert product_after["stock"] == 8
            assert product_after["cost_cents"] == 45000

            # Over-receive and foreign lines are refused.
            assert (
                client.post(
                    f"/admin/purchase-orders/{order_id}/receive",
                    headers=manager,
                    json={"items": [{"item_id": item_id, "quantity": 5}]},
                ).status_code
                == 409
            )
            assert (
                client.post(
                    f"/admin/purchase-orders/{order_id}/receive",
                    headers=manager,
                    json={"items": [{"item_id": str(uuid4()), "quantity": 1}]},
                ).status_code
                == 422
            )

            # Receive the rest: the order closes and rejects more goods.
            received = client.post(
                f"/admin/purchase-orders/{order_id}/receive",
                headers=manager,
                json={"items": [{"item_id": item_id, "quantity": 4}]},
            )
            assert received.status_code == 200, received.text
            assert received.json()["status"] == "received"
            assert received.json()["received_at"] is not None
            assert received.json()["received_by_email"] == "manager@example.com"
            assert (
                client.post(
                    f"/admin/purchase-orders/{order_id}/receive",
                    headers=manager,
                    json={"items": [{"item_id": item_id, "quantity": 1}]},
                ).status_code
                == 409
            )
            assert (
                client.post(f"/admin/purchase-orders/{order_id}/cancel", headers=manager).status_code
                == 409
            )

            # A fresh order can be cancelled; a cancelled order cannot receive.
            second = client.post(
                "/admin/purchase-orders",
                headers=manager,
                json={
                    "supplier_id": supplier_id,
                    "items": [{"product_id": product_id, "quantity": 3, "unit_cost_cents": 46000}],
                },
            ).json()
            cancelled = client.post(f"/admin/purchase-orders/{second['id']}/cancel", headers=manager)
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            assert (
                client.post(
                    f"/admin/purchase-orders/{second['id']}/cancel", headers=manager
                ).status_code
                == 409
            )
            assert (
                client.post(
                    f"/admin/purchase-orders/{second['id']}/receive",
                    headers=manager,
                    json={"items": [{"item_id": second["lines"][0]["item_id"], "quantity": 1}]},
                ).status_code
                == 409
            )

            # The single-order detail endpoint is readable by reception.
            detail = client.get(f"/admin/purchase-orders/{order_id}", headers=reception)
            assert detail.status_code == 200, detail.text
            assert detail.json()["lines"][0]["received_quantity"] == 10

            # The listing summarises by state and excludes cancelled value.
            listing = client.get("/admin/purchase-orders", headers=reception).json()
            assert listing["total"] == 2
            assert listing["summary"] == {
                "count": 2,
                "created": 0,
                "sent": 0,
                "received": 1,
                "cancelled": 1,
                "total_cents": 450000,
            }
            received_only = client.get(
                "/admin/purchase-orders", headers=reception, params={"status": "received"}
            ).json()
            assert received_only["total"] == 1
            assert received_only["items"][0]["id"] == order_id

        # The ledger keeps the receipts as intakes tied to the purchase order.
        with Session(engine) as session:
            movements = session.exec(
                select(InventoryMovement)
                .where(InventoryMovement.reference_type == "purchase_order")
                .order_by(InventoryMovement.occurred_at, InventoryMovement.id)
            ).all()
            assert [movement.movement_type for movement in movements] == ["intake", "intake"]
            assert [movement.quantity for movement in movements] == [6, 4]
            assert all(movement.reference_id is not None for movement in movements)
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
