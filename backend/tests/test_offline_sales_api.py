import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
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
    active = Member(
        first_name="Ana", last_name="Lopez", email="ana@example.com", status="active"
    )
    inactive = Member(first_name="Carla", last_name="Diaz", status="inactive")
    session.add_all([active, inactive])
    session.commit()
    return active.id, inactive.id


def _create_product(client: TestClient, headers: dict[str, str], stock: int = 10) -> str:
    response = client.post(
        "/admin/products",
        headers=headers,
        json={
            "sku": "agua-600",
            "name": "Agua 600 ml",
            "category": "Bebidas",
            "price_cents": 1500,
            "initial_stock": stock,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _stock(client: TestClient, headers: dict[str, str], product_id: str) -> int:
    listing = client.get("/admin/products?page_size=100", headers=headers)
    assert listing.status_code == 200, listing.text
    return next(item["stock"] for item in listing.json()["items"] if item["id"] == product_id)


def _open_shift(client: TestClient, headers: dict[str, str], opening_cash_cents: int = 10000) -> str:
    opened = client.post(
        "/admin/cash-sessions", headers=headers, json={"opening_cash_cents": opening_cash_cents}
    )
    assert opened.status_code == 201, opened.text
    return opened.json()["id"]


def _offline_sale(
    client_reference: str,
    product_id: str,
    *,
    quantity: int = 1,
    payment_method: str = "cash",
    member_id: str | None = None,
    sold_at: datetime | None = None,
) -> dict:
    payload = {
        "client_reference": client_reference,
        "items": [{"product_id": product_id, "quantity": quantity}],
        "payment_method": payment_method,
        "sold_at": (sold_at or datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
    }
    if member_id is not None:
        payload["member_id"] = str(member_id)
    return payload


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_sale_ticket_pdf_and_email_preview() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _ = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            product_id = _create_product(client, manager)
            _open_shift(client, reception)
            created = client.post(
                "/admin/sales",
                headers=reception,
                json={
                    "items": [{"product_id": product_id, "quantity": 2}],
                    "payment_method": "cash",
                    "member_id": str(member_id),
                },
            )
            assert created.status_code == 201, created.text
            sale = created.json()

            pdf = client.get(
                f"/admin/sales/{sale['id']}/ticket.pdf",
                headers=reception,
            )
            assert pdf.status_code == 200, pdf.text
            assert pdf.headers["content-type"].startswith("application/pdf")
            assert pdf.content.startswith(b"%PDF")
            assert "ticket.pdf" not in pdf.headers.get("content-disposition", "").lower()
            assert sale["folio"] in pdf.headers["content-disposition"]
            assert len(pdf.content) > 1000

            assert client.get(f"/admin/sales/{sale['id']}/ticket.pdf").status_code == 401
            assert client.get(
                f"/admin/sales/{sale['id']}/ticket.pdf",
                headers=trainer,
            ).status_code == 403
            assert client.get("/admin/sales/not-a-uuid/ticket.pdf", headers=reception).status_code == 422
            assert client.get(
                f"/admin/sales/{uuid4()}/ticket.pdf",
                headers=reception,
            ).status_code == 404

            import os
            os.environ["PREVIEW_MODE"] = "true"
            emailed = client.post(
                f"/admin/sales/{sale['id']}/ticket/email?recipient=socio%40example.com",
                headers=reception,
            )
            assert emailed.status_code == 200, emailed.text
            assert emailed.json()["status"] == "simulated"

            invalid_email = client.post(
                f"/admin/sales/{sale['id']}/ticket/email?recipient=correo-invalido",
                headers=reception,
            )
            assert invalid_email.status_code == 422

            import os
            os.environ.pop("PREVIEW_MODE", None)
            os.environ.pop("SMTP_HOST", None)
            public_email = client.post(
                f"/admin/sales/{sale['id']}/ticket/email?recipient=socio%40example.com",
                headers=reception,
            )
            assert public_email.status_code == 503

            missing_recipient = client.post(
                "/admin/sales",
                headers=reception,
                json={
                    "items": [{"product_id": product_id, "quantity": 1}],
                    "payment_method": "cash",
                },
            )
            assert missing_recipient.status_code == 201
            public_sale = missing_recipient.json()
            missing = client.post(
                f"/admin/sales/{public_sale['id']}/ticket/email",
                headers=reception,
            )
            assert missing.status_code == 422
    finally:
        import os
        os.environ.pop("PREVIEW_MODE", None)
        app.dependency_overrides.clear()


def test_offline_sales_sync_is_idempotent_and_keeps_timestamps() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(
                client, "accountant@example.com", "accountant-strong-password"
            )
            product_id = _create_product(client, manager)

            sold_at = datetime.now(timezone.utc) - timedelta(hours=3)
            batch = {
                "sales": [
                    _offline_sale(
                        str(uuid4()), product_id, quantity=2, sold_at=sold_at
                    ),
                    _offline_sale(
                        str(uuid4()),
                        product_id,
                        quantity=1,
                        payment_method="card",
                        sold_at=sold_at + timedelta(minutes=5),
                    ),
                ]
            }

            # A sale always belongs to a shift: syncing without one is refused.
            assert client.post(
                "/admin/sales/offline", headers=reception, json=batch
            ).status_code == 409

            cash_session_id = _open_shift(client, reception)

            synced = client.post("/admin/sales/offline", headers=reception, json=batch)
            assert synced.status_code == 200, synced.text
            body = synced.json()
            assert body["created"] == 2
            assert body["duplicates"] == 0
            assert body["rejected"] == 0
            assert [item["status"] for item in body["results"]] == ["created", "created"]
            first = body["results"][0]["sale"]
            assert first["origin"] == "offline"
            assert first["client_reference"] == batch["sales"][0]["client_reference"]
            assert first["cash_session_id"] == cash_session_id
            assert FOLIO_PATTERN.match(first["folio"])
            assert _parse(first["sold_at"]) == sold_at
            assert _parse(body["results"][1]["sale"]["sold_at"]) == sold_at + timedelta(minutes=5)

            # The sale discounted stock and joined the register totals.
            assert _stock(client, manager, product_id) == 7
            current = client.get("/admin/cash-sessions/current", headers=reception)
            assert current.status_code == 200, current.text
            session_body = current.json()
            assert session_body["sales_count"] == 2
            assert session_body["cash_sales_cents"] == 3000
            assert session_body["card_sales_cents"] == 1500
            assert session_body["total_sales_cents"] == 4500

            # Replaying the batch is harmless: same folios, no extra stock or money.
            replay = client.post("/admin/sales/offline", headers=reception, json=batch)
            assert replay.status_code == 200, replay.text
            replay_body = replay.json()
            assert replay_body["created"] == 0
            assert replay_body["duplicates"] == 2
            replay_folios = [item["sale"]["folio"] for item in replay_body["results"]]
            assert replay_folios == [
                first["folio"],
                body["results"][1]["sale"]["folio"],
            ]
            assert _stock(client, manager, product_id) == 7
            assert client.get(
                "/admin/cash-sessions/current", headers=reception
            ).json()["total_sales_cents"] == 4500

            # Offline sales are filterable for audits.
            offline = client.get("/admin/sales?origin=offline", headers=reception)
            assert offline.status_code == 200, offline.text
            assert offline.json()["total"] == 2
            online = client.get("/admin/sales?origin=online", headers=reception)
            assert online.json()["total"] == 0

            # The sync is a register operation: roles without sales.manage cannot use it.
            denied = client.post("/admin/sales/offline", headers=accountant, json=batch)
            assert denied.status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_offline_sales_reject_only_the_bad_entries() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, inactive_id = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            product_id = _create_product(client, manager, stock=3)
            _open_shift(client, reception)

            now = datetime.now(timezone.utc)
            valid_ref = str(uuid4())
            batch = {
                "sales": [
                    _offline_sale(valid_ref, product_id, quantity=2),
                    # Same reference twice: the second one is a duplicate, not a second charge.
                    _offline_sale(valid_ref, product_id, quantity=1),
                    # Not enough stock for this one.
                    _offline_sale(str(uuid4()), product_id, quantity=5),
                    # An inactive member cannot take a charge on account.
                    _offline_sale(
                        str(uuid4()),
                        product_id,
                        quantity=1,
                        payment_method="account",
                        member_id=str(inactive_id),
                    ),
                    # A timestamp in the future is a bad clock, not a sale.
                    _offline_sale(
                        str(uuid4()),
                        product_id,
                        quantity=1,
                        sold_at=now + timedelta(hours=2),
                    ),
                ]
            }

            synced = client.post("/admin/sales/offline", headers=reception, json=batch)
            assert synced.status_code == 200, synced.text
            body = synced.json()
            assert body["created"] == 1
            assert body["duplicates"] == 1
            assert body["rejected"] == 3
            statuses = [item["status"] for item in body["results"]]
            assert statuses == ["created", "duplicate", "rejected", "rejected", "rejected"]
            for item in body["results"][2:]:
                assert item["sale"] is None
                assert item["error"]

            # Only the valid sale hit the stock.
            assert _stock(client, manager, product_id) == 1

            # Structural validation happens before any sale is processed.
            assert client.post(
                "/admin/sales/offline",
                headers=reception,
                json={"sales": []},
            ).status_code == 422
            assert client.post(
                "/admin/sales/offline",
                headers=reception,
                json={"sales": [_offline_sale("x" * 65, product_id)]},
            ).status_code == 422
            assert client.post(
                "/admin/sales/offline",
                headers=reception,
                json={"sales": [_offline_sale("", product_id)]},
            ).status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_online_sales_keep_their_origin() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            product_id = _create_product(client, manager)
            _open_shift(client, reception)

            created = client.post(
                "/admin/sales",
                headers=reception,
                json={
                    "items": [{"product_id": product_id, "quantity": 1}],
                    "payment_method": "cash",
                },
            )
            assert created.status_code == 201, created.text
            assert created.json()["origin"] == "online"
            assert created.json()["client_reference"] is None

            assert client.get("/admin/sales?origin=banana", headers=reception).status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)
