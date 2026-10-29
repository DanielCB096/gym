"""Premium classes are charged through the normal sales ledger.

The seat is free while it is only reserved; the extra price is charged when the
member is marked as attending, and refunded when the reservation is cancelled
or marked as a no-show. These tests drive the whole path through the API so the
sale, the register shift and the returns stay in sync.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.main import app, get_session
from app.modules.memberships.models import Member
from test_classes_api import (
    _add_member,
    _build_engine,
    _create_catalog,
    _create_session,
    _login,
    _override,
    _seed_users,
)


def _open_shift(client: TestClient, headers: dict[str, str]) -> dict:
    opened = client.post("/admin/cash-sessions", headers=headers, json={"opening_cash_cents": 0})
    assert opened.status_code == 201, opened.text
    return opened.json()


def _reserve(client: TestClient, headers: dict[str, str], session_id: str, member_id) -> dict:
    response = client.post(
        f"/admin/classes/sessions/{session_id}/reservations",
        headers=headers,
        json={"member_id": str(member_id), "origin": "reception"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _attend(
    client: TestClient,
    headers: dict[str, str],
    reservation_id: str,
    *,
    attended: bool = True,
    payment_method: str | None = None,
):
    payload: dict[str, object] = {"attended": attended}
    if payment_method is not None:
        payload["payment_method"] = payment_method
    return client.post(
        f"/admin/classes/reservations/{reservation_id}/attendance",
        headers=headers,
        json=payload,
    )


def test_premium_class_charges_on_attendance_and_refunds_on_cancel() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            type_id, room_id = _create_catalog(client, manager)
            created = _create_session(
                client,
                manager,
                class_type_id=type_id,
                room_id=room_id,
                access_type="premium",
                extra_price_cents=15000,
            )
            assert created.status_code == 201, created.text
            session_id = created.json()["id"]
            reservation = _reserve(client, manager, session_id, member_id)
            reservation_id = reservation["id"]
            # Reserving is free: the charge is pending until attendance.
            assert reservation["charge_status"] is None

            # The charge needs an open register shift.
            missing_shift = _attend(client, manager, reservation_id, payment_method="cash")
            assert missing_shift.status_code == 409, missing_shift.text
            assert "turno de caja" in missing_shift.json()["detail"]
            assert client.get("/admin/sales", headers=manager).json()["total"] == 0

            _open_shift(client, reception)

            # A premium seat needs a payment method the first time it is charged.
            no_method = _attend(client, manager, reservation_id)
            assert no_method.status_code == 409, no_method.text
            assert "forma de pago" in no_method.json()["detail"]

            attended = _attend(client, manager, reservation_id, payment_method="cash")
            assert attended.status_code == 200, attended.text
            body = attended.json()
            assert body["status"] == "attended"
            assert body["charge_status"] == "completed"
            assert body["charge_cents"] == 15000
            assert body["charge_payment_method"] == "cash"
            assert body["charge_folio"].startswith("V-")
            assert body["charge_sale_id"]

            roster = client.get(
                f"/admin/classes/sessions/{session_id}/reservations", headers=manager
            ).json()
            assert roster["reservations"][0]["charge_status"] == "completed"
            assert roster["reservations"][0]["charge_cents"] == 15000

            # The charge is a normal sale with a service line and no stock.
            sales = client.get("/admin/sales", headers=manager).json()
            assert sales["total"] == 1
            sale = sales["items"][0]
            assert sale["total_cents"] == 15000
            assert sale["payment_method"] == "cash"
            assert sale["member_id"] == str(member_id)
            assert sale["lines"][0]["product_id"] is None
            assert sale["lines"][0]["sku"] == "CLASE"
            assert "Spinning" in sale["lines"][0]["product_name"]

            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["cash_sales_cents"] == 15000
            assert current["expected_cash_cents"] == 15000

            # Marking attendance again never charges twice.
            again = _attend(client, manager, reservation_id, payment_method="cash")
            assert again.status_code == 200
            assert again.json()["charge_status"] == "completed"
            assert client.get("/admin/sales", headers=manager).json()["total"] == 1

            # Cancelling a paid seat refunds it in the method it was paid with.
            cancelled = client.post(
                f"/admin/classes/reservations/{reservation_id}/cancel", headers=manager
            )
            assert cancelled.status_code == 200, cancelled.text
            refunded = cancelled.json()
            assert refunded["status"] == "cancelled"
            assert refunded["charge_status"] == "refunded"
            assert refunded["charge_cents"] == 15000

            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["refunds_count"] == 1
            assert current["cash_refunds_cents"] == 15000
            assert current["expected_cash_cents"] == 0

            returns = client.get("/admin/sales/returns", headers=manager).json()
            assert returns["total"] == 1
            assert returns["items"][0]["refund_method"] == "cash"
            assert returns["items"][0]["total_refund_cents"] == 15000
            assert returns["items"][0]["lines"][0]["product_id"] is None
            assert returns["items"][0]["lines"][0]["disposition"] == "write_off"
            assert client.get("/admin/sales", headers=manager).json()["items"][0]["status"] == "refunded"
    finally:
        app.dependency_overrides.clear()


def test_premium_account_charge_respects_credit_and_no_show_refunds() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member = Member(
            first_name="Lim",
            last_name="Demo",
            email="limite@example.com",
            status="active",
            credit_limit_cents=10000,
        )
        session.add(member)
        session.commit()
        member_id = member.id

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            type_id, room_id = _create_catalog(client, manager)
            shift = _open_shift(client, reception)

            expensive = _create_session(
                client,
                manager,
                class_type_id=type_id,
                room_id=room_id,
                access_type="premium",
                extra_price_cents=15000,
            ).json()["id"]
            reservation = _reserve(client, manager, expensive, member_id)

            # A charge on account cannot exceed the member's credit.
            over_limit = _attend(
                client, manager, reservation["id"], payment_method="account"
            )
            assert over_limit.status_code == 409, over_limit.text
            assert "crédito" in over_limit.json()["detail"]

            # Card works and is not part of the member account.
            charged = _attend(client, manager, reservation["id"], payment_method="card")
            assert charged.status_code == 200, charged.text
            assert charged.json()["charge_payment_method"] == "card"
            assert client.get(
                f"/admin/member-accounts/{member_id}", headers=manager
            ).json()["summary"]["balance_cents"] == 0

            # A card refund never touches the drawer, so it works with no shift.
            closed = client.post(
                f"/admin/cash-sessions/{shift['id']}/close",
                headers=reception,
                json={"counted_cash_cents": 0},
            )
            assert closed.status_code == 200, closed.text
            no_show = _attend(client, manager, reservation["id"], attended=False)
            assert no_show.status_code == 200, no_show.text
            assert no_show.json()["charge_status"] == "refunded"
            card_return = client.get("/admin/sales/returns", headers=manager).json()["items"][0]
            assert card_return["refund_method"] == "card"
            assert card_return["cash_session_id"] is None

            # An affordable premium class can be charged to the account and is
            # credited back when the seat is cancelled.
            _open_shift(client, reception)
            cheaper = _create_session(
                client,
                manager,
                class_type_id=type_id,
                room_id=room_id,
                access_type="premium",
                extra_price_cents=5000,
            ).json()["id"]
            second = _reserve(client, manager, cheaper, member_id)
            on_account = _attend(
                client, manager, second["id"], payment_method="account"
            )
            assert on_account.status_code == 200, on_account.text
            assert on_account.json()["charge_payment_method"] == "account"
            account = client.get(
                f"/admin/member-accounts/{member_id}", headers=manager
            ).json()["summary"]
            assert account["balance_cents"] == 5000
            assert account["charges_cents"] == 5000

            cancelled = client.post(
                f"/admin/classes/reservations/{second['id']}/cancel", headers=manager
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["charge_status"] == "refunded"
            account = client.get(
                f"/admin/member-accounts/{member_id}", headers=manager
            ).json()["summary"]
            assert account["balance_cents"] == 0
            assert account["credits_cents"] == 5000
    finally:
        app.dependency_overrides.clear()


def test_premium_waitlist_promotion_keeps_the_charge_pending() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        first = _add_member(session, first="Ana")
        second = _add_member(session, first="Beto")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            type_id, room_id = _create_catalog(client, manager)
            session_id = _create_session(
                client,
                manager,
                class_type_id=type_id,
                room_id=room_id,
                capacity=1,
                access_type="premium",
                extra_price_cents=8000,
            ).json()["id"]
            seated = _reserve(client, manager, session_id, first)
            waiting = _reserve(client, manager, session_id, second)
            assert waiting["status"] == "waitlist"
            assert waiting["charge_status"] is None

            # There is no shift open: cancelling a free seat still works.
            cancelled = client.post(
                f"/admin/classes/reservations/{seated['id']}/cancel", headers=manager
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["charge_status"] is None
            assert client.get("/admin/sales", headers=manager).json()["total"] == 0

            roster = client.get(
                f"/admin/classes/sessions/{session_id}/reservations", headers=manager
            ).json()
            promoted = next(item for item in roster["reservations"] if item["member_id"] == str(second))
            assert promoted["status"] == "reserved"
            # Promotion keeps the charge pending; nothing was sold yet.
            assert promoted["charge_status"] is None

            _open_shift(client, reception)
            charged = _attend(client, manager, promoted["id"], payment_method="card")
            assert charged.status_code == 200, charged.text
            assert charged.json()["charge_status"] == "completed"
            assert charged.json()["charge_cents"] == 8000
    finally:
        app.dependency_overrides.clear()


def test_cash_premium_refund_requires_an_open_register() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            type_id, room_id = _create_catalog(client, manager)
            session_id = _create_session(
                client,
                manager,
                class_type_id=type_id,
                room_id=room_id,
                access_type="premium",
                extra_price_cents=12000,
            ).json()["id"]
            shift = _open_shift(client, reception)
            reservation = _reserve(client, manager, session_id, member_id)
            charged = _attend(client, manager, reservation["id"], payment_method="cash")
            assert charged.status_code == 200, charged.text

            closed = client.post(
                f"/admin/cash-sessions/{shift['id']}/close",
                headers=reception,
                json={"counted_cash_cents": 12000},
            )
            assert closed.status_code == 200, closed.text
            assert closed.json()["expected_cash_cents"] == 12000

            # Cash left the drawer, so the refund must belong to a shift.
            blocked = client.post(
                f"/admin/classes/reservations/{reservation['id']}/cancel", headers=manager
            )
            assert blocked.status_code == 409, blocked.text
            assert "turno de caja" in blocked.json()["detail"]

            # The failed cancellation was rolled back: the seat stays attended.
            roster = client.get(
                f"/admin/classes/sessions/{session_id}/reservations", headers=manager
            ).json()
            assert roster["reservations"][0]["status"] == "attended"
            assert roster["reservations"][0]["charge_status"] == "completed"

            second_shift = _open_shift(client, reception)
            cancelled = client.post(
                f"/admin/classes/reservations/{reservation['id']}/cancel", headers=manager
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["charge_status"] == "refunded"
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["id"] == second_shift["id"]
            assert current["cash_refunds_cents"] == 12000
            assert current["expected_cash_cents"] == -12000
    finally:
        app.dependency_overrides.clear()


def test_register_refunds_a_service_with_the_manager_permission() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id = _add_member(session, first="Ana")

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            type_id, room_id = _create_catalog(client, manager)
            _open_shift(client, reception)
            session_id = _create_session(
                client,
                manager,
                class_type_id=type_id,
                room_id=room_id,
                access_type="premium",
                extra_price_cents=15000,
            ).json()["id"]
            reservation = _reserve(client, manager, session_id, member_id)
            charged = _attend(client, manager, reservation["id"], payment_method="cash")
            assert charged.status_code == 200, charged.text
            sale_id = charged.json()["charge_sale_id"]

            refund_url = f"/admin/sales/{sale_id}/service-refund"
            reason = {"reason": "Cobro duplicado en recepción"}

            # The register is a counter operation; refunding a service is not.
            assert client.post(refund_url, headers=reception, json=reason).status_code == 403
            assert client.post(refund_url, headers=trainer, json=reason).status_code == 403
            assert client.post(refund_url, headers=manager, json={"reason": ""}).status_code == 422
            assert client.get("/admin/sales", headers=manager).json()["items"][0]["status"] == "completed"

            refunded = client.post(refund_url, headers=manager, json=reason)
            assert refunded.status_code == 201, refunded.text
            body = refunded.json()
            assert body["refund_method"] == "cash"
            assert body["total_refund_cents"] == 15000
            assert body["reason"] == reason["reason"]
            assert body["lines"][0]["product_id"] is None
            assert body["lines"][0]["disposition"] == "write_off"
            assert body["cash_session_id"]

            # The sale is refunded, the drawer shows the outflow and the seat
            # keeps its attendance: the refund does not rewrite the class.
            sale = client.get("/admin/sales", headers=manager).json()["items"][0]
            assert sale["status"] == "refunded"
            current = client.get("/admin/cash-sessions/current", headers=reception).json()
            assert current["cash_refunds_cents"] == 15000
            assert current["expected_cash_cents"] == 0
            roster = client.get(
                f"/admin/classes/sessions/{session_id}/reservations", headers=manager
            ).json()
            assert roster["reservations"][0]["status"] == "attended"
            assert roster["reservations"][0]["charge_status"] == "refunded"

            # A second refund is a conflict, never a second payout.
            again = client.post(refund_url, headers=manager, json=reason)
            assert again.status_code == 409, again.text
            assert client.get("/admin/sales/returns", headers=manager).json()["total"] == 1

            # A product sale is not a service: it keeps the returns flow.
            product = client.post(
                "/admin/products",
                headers=manager,
                json={
                    "sku": "agua-600",
                    "name": "Agua 600 ml",
                    "category": "Bebidas",
                    "price_cents": 1500,
                    "initial_stock": 5,
                },
            )
            assert product.status_code == 201, product.text
            product_sale = client.post(
                "/admin/sales",
                headers=reception,
                json={
                    "items": [{"product_id": product.json()["id"], "quantity": 1}],
                    "payment_method": "cash",
                },
            )
            assert product_sale.status_code == 201, product_sale.text
            wrong = client.post(
                f"/admin/sales/{product_sale.json()['id']}/service-refund",
                headers=manager,
                json={"reason": "Prueba"},
            )
            assert wrong.status_code == 422, wrong.text
            assert "reserva de clase" in wrong.json()["detail"]
    finally:
        app.dependency_overrides.clear()
