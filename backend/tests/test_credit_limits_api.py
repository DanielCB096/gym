from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member
from app.timezone import club_date, club_timezone, local_midnight


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


def _create_product(
    client: TestClient,
    headers: dict[str, str],
    *,
    sku: str = "agua-600",
    name: str = "Agua 600 ml",
    price_cents: int = 1500,
    initial_stock: int = 40,
) -> str:
    response = client.post(
        "/admin/products",
        headers=headers,
        json={
            "sku": sku,
            "name": name,
            "category": "Bebidas",
            "price_cents": price_cents,
            "initial_stock": initial_stock,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _local_day(days_ago: int) -> date:
    return club_date(datetime.now(timezone.utc)) - timedelta(days=days_ago)


def _sold_at(days_ago: int) -> str:
    noon = local_midnight(_local_day(days_ago), club_timezone()) + timedelta(hours=12)
    return noon.isoformat()


def _offline_account_entry(
    reference: str, product_id: str, member_id, quantity: int, days_ago: int
) -> dict:
    return {
        "client_reference": reference,
        "items": [{"product_id": product_id, "quantity": quantity}],
        "payment_method": "account",
        "member_id": str(member_id),
        "sold_at": _sold_at(days_ago),
    }


def test_credit_limit_lifecycle_and_permissions() -> None:
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
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")

            updated = client.patch(
                f"/admin/member-accounts/{member_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": 5000},
            )
            assert updated.status_code == 200, updated.text
            body = updated.json()
            assert body["credit_limit_cents"] == 5000
            assert body["credit_available_cents"] == 5000
            assert body["over_limit"] is False
            assert body["balance_cents"] == 0
            assert body["aging"] == {
                "current_cents": 0,
                "days_31_60_cents": 0,
                "days_61_90_cents": 0,
                "over_90_cents": 0,
            }

            # A configured limit by itself does not create a receivable.
            directory = client.get("/admin/member-accounts", headers=manager).json()
            assert directory["items"] == []
            assert directory["members_with_balance"] == 0

            # Setting credit policy belongs to the owner/manager, not the counter
            # or the read-only accountant.
            for headers in (reception, accountant, trainer):
                assert client.patch(
                    f"/admin/member-accounts/{member_id}/credit-limit",
                    headers=headers,
                    json={"credit_limit_cents": 1000},
                ).status_code == 403

            assert client.patch(
                f"/admin/member-accounts/{member_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": -1},
            ).status_code == 422
            assert client.patch(
                f"/admin/member-accounts/{uuid4()}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": 1000},
            ).status_code == 404

            cleared = client.patch(
                f"/admin/member-accounts/{member_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": None},
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["credit_limit_cents"] is None
            assert cleared.json()["credit_available_cents"] is None
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_credit_limit_blocks_charges_and_frees_credit() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, other_id, _ = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            product_id = _create_product(client, manager)
            client.post(
                "/admin/cash-sessions", headers=reception, json={"opening_cash_cents": 10000}
            )
            client.patch(
                f"/admin/member-accounts/{member_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": 5000},
            )

            def charge(quantity: int, member=member_id):
                return client.post(
                    "/admin/sales",
                    headers=reception,
                    json={
                        "items": [{"product_id": product_id, "quantity": quantity}],
                        "payment_method": "account",
                        "member_id": str(member),
                    },
                )

            first = charge(2)
            assert first.status_code == 201, first.text
            assert client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            ).json()["summary"]["credit_available_cents"] == 2000

            # 3000 more would exceed the 5000 limit.
            blocked = charge(2)
            assert blocked.status_code == 409, blocked.text
            assert "crédito disponible" in blocked.json()["detail"]

            assert charge(1).status_code == 201
            assert charge(1).status_code == 409

            # A payment clears the oldest debt and reopens the limit.
            payment = client.post(
                f"/admin/member-accounts/{member_id}/payments",
                headers=reception,
                json={"amount_cents": 1000, "method": "cash"},
            )
            assert payment.status_code == 201, payment.text
            assert payment.json()["balance_cents"] == 3500

            at_limit = charge(1)
            assert at_limit.status_code == 201, at_limit.text
            assert client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            ).json()["summary"]["credit_available_cents"] == 0
            assert charge(1).status_code == 409

            # An account refund also frees credit: the member can charge again.
            returned = client.post(
                f"/admin/sales/{at_limit.json()['id']}/returns",
                headers=reception,
                json={
                    "items": [
                        {
                            "sale_item_id": at_limit.json()["lines"][0]["sale_item_id"],
                            "quantity": 1,
                            "disposition": "restock",
                        }
                    ],
                    "reason": "Prueba de crédito",
                },
            )
            assert returned.status_code == 201, returned.text
            assert returned.json()["refund_method"] == "account"
            assert charge(1).status_code == 201

            # A zero limit blocks every charge; clearing it restores the old
            # "no limit" behavior.
            client.patch(
                f"/admin/member-accounts/{other_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": 0},
            )
            assert charge(1, other_id).status_code == 409
            client.patch(
                f"/admin/member-accounts/{other_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": None},
            )
            unlimited = charge(1, other_id)
            assert unlimited.status_code == 201, unlimited.text
            assert unlimited.json()["total_cents"] == 1500
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_aging_applies_payments_fifo_and_uses_club_days() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, boundary_member_id, _ = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            product_id = _create_product(
                client, manager, sku="agua-aging", name="Agua aging", price_cents=100,
                initial_stock=1000,
            )
            client.post(
                "/admin/cash-sessions", headers=reception, json={"opening_cash_cents": 0}
            )

            batch = client.post(
                "/admin/sales/offline",
                headers=reception,
                json={
                    "sales": [
                        _offline_account_entry("aging-old", product_id, member_id, 100, 100),
                        _offline_account_entry("aging-mid", product_id, member_id, 50, 45),
                        _offline_account_entry("aging-new", product_id, member_id, 30, 5),
                    ]
                },
            )
            assert batch.status_code == 200, batch.text
            assert [item["status"] for item in batch.json()["results"]] == [
                "created",
                "created",
                "created",
            ]

            # 12000 paid FIFO: the 100-day charge is settled, 2000 of the 45-day
            # charge is settled, and 3000 + 3000 remain.
            payment = client.post(
                f"/admin/member-accounts/{member_id}/payments",
                headers=reception,
                json={"amount_cents": 12000, "method": "cash"},
            )
            assert payment.status_code == 201, payment.text
            assert payment.json()["balance_cents"] == 6000

            statement = client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            ).json()
            assert statement["summary"]["balance_cents"] == 6000
            assert statement["summary"]["aging"] == {
                "current_cents": 3000,
                "days_31_60_cents": 3000,
                "days_61_90_cents": 0,
                "over_90_cents": 0,
            }

            # Boundary days: exactly 30/31/60/61/90/91 days old. Each charge is
            # one peso and there are no credits.
            boundary_entries = [
                _offline_account_entry(f"aging-{days}", product_id, boundary_member_id, 1, days)
                for days in (30, 31, 60, 61, 90, 91)
            ]
            boundary_batch = client.post(
                "/admin/sales/offline",
                headers=reception,
                json={"sales": boundary_entries},
            )
            assert boundary_batch.status_code == 200, boundary_batch.text
            assert all(
                item["status"] == "created" for item in boundary_batch.json()["results"]
            )

            boundary = client.get(
                f"/admin/member-accounts/{boundary_member_id}", headers=reception
            ).json()
            assert boundary["summary"]["aging"] == {
                "current_cents": 100,
                "days_31_60_cents": 200,
                "days_61_90_cents": 200,
                "over_90_cents": 100,
            }

            directory = client.get("/admin/member-accounts", headers=reception).json()
            assert directory["as_of"] == club_date(datetime.now(timezone.utc)).isoformat()
            assert directory["total_receivable_cents"] == 6600
            assert directory["aging"] == {
                "current_cents": 3100,
                "days_31_60_cents": 3200,
                "days_61_90_cents": 200,
                "over_90_cents": 100,
            }
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_lowering_the_limit_marks_the_account_over_limit() -> None:
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
                "/admin/cash-sessions", headers=reception, json={"opening_cash_cents": 0}
            )
            client.patch(
                f"/admin/member-accounts/{member_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": 5000},
            )
            charge = {
                "items": [{"product_id": product_id, "quantity": 2}],
                "payment_method": "account",
                "member_id": str(member_id),
            }
            assert client.post("/admin/sales", headers=reception, json=charge).status_code == 201

            lowered = client.patch(
                f"/admin/member-accounts/{member_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": 1000},
            )
            assert lowered.status_code == 200, lowered.text
            assert lowered.json()["over_limit"] is True
            assert lowered.json()["credit_available_cents"] == -2000

            over = client.get(
                "/admin/member-accounts", headers=reception, params={"over_limit": "true"}
            ).json()
            assert over["total"] == 1
            assert over["over_limit_members"] == 1
            assert over["items"][0]["member_id"] == str(member_id)
            under = client.get(
                "/admin/member-accounts", headers=reception, params={"over_limit": "false"}
            ).json()
            assert under["items"] == []

            # The account is over its limit, so a new charge is refused.
            assert client.post("/admin/sales", headers=reception, json=charge).status_code == 409

            restored = client.patch(
                f"/admin/member-accounts/{member_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": 5000},
            )
            assert restored.json()["over_limit"] is False
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_offline_account_charge_is_rejected_by_the_credit_limit() -> None:
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
                "/admin/cash-sessions", headers=reception, json={"opening_cash_cents": 0}
            )
            client.patch(
                f"/admin/member-accounts/{member_id}/credit-limit",
                headers=manager,
                json={"credit_limit_cents": 1000},
            )

            synced = client.post(
                "/admin/sales/offline",
                headers=reception,
                json={
                    "sales": [
                        _offline_account_entry(
                            "credit-rejected", product_id, member_id, 1, 0
                        )
                    ]
                },
            )
            assert synced.status_code == 200, synced.text
            result = synced.json()["results"][0]
            assert result["status"] == "rejected"
            assert "crédito disponible" in result["error"]
            assert client.get("/admin/sales", headers=reception).json()["total"] == 0
            assert client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            ).json()["summary"]["balance_cents"] == 0
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
