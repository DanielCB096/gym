"""Tests for the read-only reports module.

Reports only aggregate, so the fixtures write rows straight into the tables with
backdated timestamps. That is exactly what the module reads, and it keeps the
tests focused on the aggregation rules instead of replaying the point-of-sale or
the billing flow.
"""

from collections.abc import Iterator
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.access.models import AccessEvent
from app.modules.billing.models import Invoice, InvoicePayment
from app.modules.classes.models import ClassReservation, ClassSession, ClassType
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory.models import (
    CashSession,
    InventoryMovement,
    InventoryStock,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Sale,
    SaleItem,
    SaleReturn,
    SaleReturnItem,
    Supplier,
)
from app.modules.maintenance.models import Equipment, MaintenanceRecord, MaintenanceTicket
from app.modules.memberships.models import (
    Member,
    Membership,
    MembershipEvent,
    Payment,
    PaymentAttempt,
    Plan,
)
from app.modules.routines.models import (
    BodyMeasurement,
    Routine,
    RoutineAssignment,
    WorkoutLog,
)
from app.modules.reports.service import resolve_period
from app.timezone import club_date

TODAY = date.today()
PERIOD_FROM = TODAY - timedelta(days=14)
PERIOD_TO = TODAY
OUTSIDE = TODAY - timedelta(days=60)
PERIOD_PARAMS = {"date_from": PERIOD_FROM.isoformat(), "date_to": PERIOD_TO.isoformat()}


def _at(day: date, hour: int = 12) -> datetime:
    return datetime.combine(day, time(hour=hour), tzinfo=timezone.utc)


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


def _override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_users(session: Session) -> None:
    ensure_default_access_control(session)
    register_user(session, email="owner@example.com", password="owner-strong-password", role_codes=("owner",))
    register_user(session, email="manager@example.com", password="manager-strong-password", role_codes=("manager",))
    register_user(session, email="accountant@example.com", password="accountant-strong-password", role_codes=("accountant",))
    register_user(session, email="reception@example.com", password="reception-strong-password", role_codes=("reception",))
    register_user(session, email="trainer@example.com", password="trainer-strong-password", role_codes=("trainer",))
    register_user(session, email="maint@example.com", password="maint-strong-password", role_codes=("maintenance",))


def _seed_dataset(session: Session) -> None:
    """Two weeks of history plus a decoy two months back.

    Inside the period: 50 000 c of counter sales, 90 000 c of membership charges,
    four access events, one class with five reservations, one workout, one
    measurement and one paid maintenance record. Everything seeded ``OUTSIDE``
    must be ignored by the period filter.
    """

    monthly = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=50000)
    annual = Plan(code="ANNUAL", name="Anual", duration_days=365, price_cents=549900)
    day_pass = Plan(code="DAY", name="Pase de día", duration_days=1, price_cents=1500)
    session.add_all([monthly, annual, day_pass])
    session.flush()

    members = {
        "m1": Member(first_name="Socio", last_name="Uno", status="active", created_at=_at(TODAY - timedelta(days=5))),
        "m2": Member(first_name="Socio", last_name="Dos", status="active", created_at=_at(TODAY - timedelta(days=5))),
        "m3": Member(first_name="Socio", last_name="Tres", status="active", created_at=_at(OUTSIDE)),
        "m4": Member(first_name="Socio", last_name="Cuatro", status="active", created_at=_at(OUTSIDE)),
        "m5": Member(first_name="Socio", last_name="Cinco", status="inactive", created_at=_at(OUTSIDE)),
        "m6": Member(first_name="Socio", last_name="Seis", status="pending", created_at=_at(OUTSIDE)),
    }
    session.add_all(list(members.values()))
    session.flush()

    memberships = {
        "m1": Membership(
            member_id=members["m1"].id,
            plan_id=monthly.id,
            status="active",
            starts_at=_at(TODAY - timedelta(days=10)),
            ends_at=_at(TODAY + timedelta(days=20)),
        ),
        "m2": Membership(
            member_id=members["m2"].id,
            plan_id=monthly.id,
            status="active",
            starts_at=_at(TODAY - timedelta(days=27)),
            ends_at=_at(TODAY + timedelta(days=3)),  # expiring within a week
        ),
        "m3": Membership(
            member_id=members["m3"].id,
            plan_id=annual.id,
            status="active",
            starts_at=_at(TODAY - timedelta(days=100)),
            ends_at=_at(TODAY + timedelta(days=265)),
        ),
        "m4": Membership(
            member_id=members["m4"].id,
            plan_id=day_pass.id,
            status="active",
            starts_at=_at(TODAY),
            ends_at=_at(TODAY + timedelta(days=1)),
        ),
        "m5": Membership(
            member_id=members["m5"].id,
            plan_id=monthly.id,
            status="cancelled",
            starts_at=_at(TODAY - timedelta(days=40)),
            ends_at=_at(TODAY - timedelta(days=10)),
        ),
        "m6": Membership(
            member_id=members["m6"].id,
            plan_id=annual.id,
            status="frozen",
            starts_at=_at(TODAY - timedelta(days=5)),
            ends_at=_at(TODAY + timedelta(days=25)),
        ),
    }
    session.add_all(list(memberships.values()))
    session.flush()

    session.add_all(
        [
            MembershipEvent(
                membership_id=memberships["m1"].id,
                event_type="payment_confirmed",
                actor_type="provider",
                occurred_at=_at(TODAY - timedelta(days=2)),
            ),
            MembershipEvent(
                membership_id=memberships["m5"].id,
                event_type="cancelled",
                actor_type="employee",
                occurred_at=_at(TODAY - timedelta(days=2)),
            ),
            MembershipEvent(
                membership_id=memberships["m3"].id,
                event_type="payment_confirmed",
                actor_type="provider",
                occurred_at=_at(OUTSIDE),
            ),
        ]
    )

    def _payment(membership_key: str, *, amount: int, method: str, day: date, attempt_number: int) -> None:
        membership = memberships[membership_key]
        attempt = PaymentAttempt(
            membership_id=membership.id,
            method=method,
            idempotency_key=f"key-{uuid4().hex}",
            request_fingerprint=uuid4().hex,
            attempt_number=attempt_number,
            amount_cents=amount,
            status="succeeded",
            due_at=_at(day),
            resolved_at=_at(day),
        )
        session.add(attempt)
        session.flush()
        session.add(
            Payment(
                payment_attempt_id=attempt.id,
                member_id=membership.member_id,
                membership_id=membership.id,
                amount_cents=amount,
                currency="MXN",
                method=method,
                paid_at=_at(day),
            )
        )

    _payment("m1", amount=50000, method="cash", day=TODAY - timedelta(days=2), attempt_number=1)
    _payment("m2", amount=40000, method="transfer", day=TODAY - timedelta(days=2), attempt_number=1)
    _payment("m5", amount=99999, method="cash", day=OUTSIDE, attempt_number=1)

    beverage = Product(sku="AGUA", name="Agua 600ml", category="Bebidas", price_cents=1000, cost_cents=400, stock_min=6)
    supplement = Product(sku="PROT", name="Proteína 1kg", category="Suplementos", price_cents=10000, cost_cents=7000, stock_min=2)
    session.add_all([beverage, supplement])
    session.flush()

    cash_session = CashSession(
        status="closed",
        opened_at=_at(TODAY - timedelta(days=3), 9),
        opening_cash_cents=50000,
        closed_at=_at(TODAY - timedelta(days=3), 20),
        expected_cash_cents=30000,
        counted_cash_cents=31500,
        difference_cents=1500,
    )
    session.add(cash_session)
    session.flush()

    def _sale(folio: str, *, total: int, method: str, day: date, item: tuple) -> None:
        sale = Sale(
            folio=folio,
            cash_session_id=cash_session.id,
            subtotal_cents=total,
            discount_cents=0,
            tax_cents=0,
            total_cents=total,
            payment_method=method,
            status="completed",
            sold_at=_at(day),
        )
        session.add(sale)
        session.flush()
        product, quantity, unit_price = item
        session.add(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=quantity,
                unit_price_cents=unit_price,
                line_total_cents=quantity * unit_price,
            )
        )

    _sale("V-001", total=30000, method="cash", day=TODAY - timedelta(days=3), item=(beverage, 30, 1000))
    _sale("V-002", total=20000, method="card", day=TODAY, item=(supplement, 2, 10000))
    _sale("V-003", total=99999, method="cash", day=OUTSIDE, item=(beverage, 1, 99999))

    def _access(hour: int, *, authorized: bool, source: str, day_offset: int = 1) -> None:
        session.add(
            AccessEvent(
                event_id=uuid4(),
                member_id=members["m1"].id,
                reader_id="TURN-1",
                direction="entry",
                authorized=authorized,
                reason="entry_allowed" if authorized else "membership_not_active",
                source=source,
                occurred_at=_at(TODAY - timedelta(days=day_offset), hour),
            )
        )

    # Stored in UTC but reported in the club's local hour (Mexico is UTC-6), so
    # these land at 10:00 and 11:00 on the report.
    _access(16, authorized=True, source="reader")
    _access(16, authorized=True, source="reader")
    _access(17, authorized=False, source="reader")
    _access(17, authorized=True, source="manual")
    _access(15, authorized=False, source="reader", day_offset=40)  # outside

    class_type = ClassType(name="Spinning")
    session.add(class_type)
    session.flush()
    class_session = ClassSession(
        title="Spinning 18:00",
        class_type_id=class_type.id,
        starts_at=_at(TODAY - timedelta(days=2), 18),
        ends_at=_at(TODAY - timedelta(days=2), 19),
        capacity=20,
        status="scheduled",
    )
    session.add(class_session)
    session.flush()
    for key, status in (("m1", "attended"), ("m2", "attended"), ("m3", "attended"), ("m4", "reserved"), ("m5", "no_show")):
        session.add(
            ClassReservation(session_id=class_session.id, member_id=members[key].id, status=status)
        )

    routine = Routine(name="Full body", version=1, status="active")
    session.add(routine)
    session.flush()
    assignment = RoutineAssignment(
        routine_id=routine.id,
        routine_version=1,
        member_id=members["m1"].id,
        start_date=TODAY - timedelta(days=20),
    )
    session.add(assignment)
    session.flush()
    session.add_all(
        [
            WorkoutLog(
                assignment_id=assignment.id,
                member_id=members["m1"].id,
                routine_id=routine.id,
                routine_version=1,
                performed_at=TODAY - timedelta(days=1),
                duration_minutes=45,
                status="logged",
            ),
            WorkoutLog(
                assignment_id=assignment.id,
                member_id=members["m1"].id,
                routine_id=routine.id,
                routine_version=1,
                performed_at=OUTSIDE,
                duration_minutes=60,
                status="logged",
            ),
            BodyMeasurement(member_id=members["m1"].id, measured_at=_at(TODAY - timedelta(days=1)), weight_kg=72.5),
            BodyMeasurement(member_id=members["m1"].id, measured_at=_at(OUTSIDE), weight_kg=74.0),
        ]
    )

    treadmill = Equipment(
        name="Caminadora",
        category="Cardio",
        location="Cardio",
        status="operational",
        next_preventive_due=TODAY - timedelta(days=1),
    )
    bike = Equipment(name="Bicicleta", category="Cardio", location="Cardio", status="operational")
    session.add_all([treadmill, bike])
    session.flush()
    session.add_all(
        [
            MaintenanceRecord(
                equipment_id=treadmill.id,
                kind="preventive",
                summary="Lubricación de banda",
                performed_at=_at(TODAY - timedelta(days=4)),
                cost_cents=10000,
            ),
            MaintenanceRecord(
                equipment_id=bike.id,
                kind="corrective",
                summary="Cambio de rodamiento",
                performed_at=_at(OUTSIDE),
                cost_cents=5000,
            ),
        ]
    )
    session.add_all(
        [
            MaintenanceTicket(
                code="MT-OPEN",
                equipment_id=treadmill.id,
                title="Banda desgastada",
                kind="corrective",
                severity="critical",
                status="open",
                created_at=_at(TODAY - timedelta(days=4)),
            ),
            MaintenanceTicket(
                code="MT-OLD",
                equipment_id=bike.id,
                title="Ruido viejo",
                kind="corrective",
                severity="low",
                status="resolved",
                resolution_notes="Se ajustó la banda",
                resolved_at=_at(OUTSIDE),
                created_at=_at(OUTSIDE),
            ),
        ]
    )
    session.commit()


def test_reports_require_finance_permission() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            assert client.get("/admin/reports/overview").status_code == 401

            owner = _login(client, "owner@example.com", "owner-strong-password")
            manager = _login(client, "manager@example.com", "manager-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            maintenance = _login(client, "maint@example.com", "maint-strong-password")

            # Owner, manager and accountant read the financial reports...
            for headers in (owner, manager, accountant):
                assert client.get("/admin/reports/overview", headers=headers).status_code == 200
                assert client.get("/admin/reports/revenue", headers=headers).status_code == 200
                assert client.get("/admin/reports/export", headers=headers).status_code == 200
            # ...front desk, trainers and maintenance staff do not.
            for headers in (reception, trainer, maintenance):
                assert client.get("/admin/reports/overview", headers=headers).status_code == 403
                assert client.get("/admin/reports/revenue", headers=headers).status_code == 403
                assert client.get("/admin/reports/export", headers=headers).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_overview_and_revenue_aggregate_the_period() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        _seed_dataset(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")

            overview = client.get("/admin/reports/overview", headers=manager, params=PERIOD_PARAMS).json()
            assert overview["period"]["days"] == 15
            assert overview["pos_cents"] == 50000
            assert overview["sales_count"] == 2
            assert overview["average_ticket_cents"] == 25000
            assert overview["membership_cents"] == 90000
            assert overview["payments_count"] == 2
            # Recurring value: two 30-day plans plus one annual plan normalised to
            # a month; the day pass is not recurring and is left out.
            assert overview["mrr_expected_cents"] == 50000 * 2 + round(549900 * 30 / 365)
            assert overview["maintenance_cost_cents"] == 10000
            assert overview["maintenance_records"] == 1
            assert overview["new_members"] == 2
            # The monthly membership ending in three days and the day pass
            # ending tomorrow both fall inside the seven-day window.
            assert overview["members_expiring"] == 2
            assert overview["tickets_open"] == 1
            assert overview["tickets_critical"] == 1
            assert overview["equipment_total"] == 2

            # The daily series fills every day of the window, even empty ones.
            assert len(overview["revenue_by_day"]) == 15
            assert sum(day["pos_cents"] for day in overview["revenue_by_day"]) == 50000
            assert sum(day["membership_cents"] for day in overview["revenue_by_day"]) == 90000
            by_day = {day["day"]: day for day in overview["revenue_by_day"]}
            assert by_day[TODAY.isoformat()]["pos_cents"] == 20000
            assert by_day[PERIOD_FROM.isoformat()]["total_cents"] == 0

            revenue = client.get("/admin/reports/revenue", headers=manager, params=PERIOD_PARAMS).json()
            assert {row["label"]: row["amount_cents"] for row in revenue["pos_by_method"]} == {
                "cash": 30000,
                "card": 20000,
            }
            assert {row["label"]: row["amount_cents"] for row in revenue["membership_by_method"]} == {
                "cash": 50000,
                "transfer": 40000,
            }
            assert {row["label"]: row["amount_cents"] for row in revenue["by_category"]} == {
                "Bebidas": 30000,
                "Suplementos": 20000,
            }
            assert [row["sku"] for row in revenue["top_products"]] == ["AGUA", "PROT"]
            assert revenue["cash_sessions_opened"] == 1
            assert revenue["cash_sessions_closed"] == 1
            assert revenue["cash_difference_cents"] == 1500

            # A single-day window keeps the closing day inclusive.
            single = client.get(
                "/admin/reports/revenue",
                headers=manager,
                params={"date_from": TODAY.isoformat(), "date_to": TODAY.isoformat()},
            ).json()
            assert single["pos_cents"] == 20000
            assert single["sales_count"] == 1
            assert len(single["by_day"]) == 1

            # The decoy two months back only shows up when it is asked for.
            wide = client.get(
                "/admin/reports/overview",
                headers=manager,
                params={"date_from": OUTSIDE.isoformat(), "date_to": TODAY.isoformat()},
            ).json()
            assert wide["pos_cents"] == 50000 + 99999
            assert wide["maintenance_cost_cents"] == 15000
    finally:
        app.dependency_overrides.clear()


def _seed_ppd_receivables(session: Session) -> None:
    def invoice(*, folio: int, total_cents: int, stamped_at: datetime) -> Invoice:
        return Invoice(
            series="A",
            folio=folio,
            status="stamped",
            origin_type="sale",
            origin_id=uuid4(),
            origin_reference=f"V-20260901-{folio}",
            receptor_rfc="XAXX010101000",
            receptor_name="Ana López",
            receptor_tax_regime="612",
            receptor_postal_code="06600",
            receptor_cfdi_use="G03",
            currency="MXN",
            subtotal_cents=total_cents,
            tax_cents=0,
            total_cents=total_cents,
            tax_rate_percent=0,
            payment_form="99",
            payment_method="PPD",
            uuid=str(uuid4()),
            stamped_at=stamped_at,
            idempotency_key=f"invoice-{folio}",
            request_fingerprint="f" * 64,
        )

    open_invoice = invoice(
        folio=301, total_cents=116000, stamped_at=_at(TODAY - timedelta(days=45))
    )
    paid_invoice = invoice(
        folio=302, total_cents=50000, stamped_at=_at(TODAY - timedelta(days=120))
    )
    session.add_all([open_invoice, paid_invoice])
    session.flush()

    def complement(
        invoice_row: Invoice,
        *,
        folio: int,
        partiality: int,
        status: str,
        payment_form: str,
        amount_cents: int,
        prior_balance_cents: int,
        outstanding_balance_cents: int,
        uuid_value: str | None = None,
    ) -> None:
        session.add(
            InvoicePayment(
                invoice_id=invoice_row.id,
                series="P",
                folio=folio,
                status=status,
                partiality_number=partiality,
                amount_cents=amount_cents,
                currency="MXN",
                payment_form=payment_form,
                paid_on=TODAY,
                prior_balance_cents=prior_balance_cents,
                outstanding_balance_cents=outstanding_balance_cents,
                uuid=uuid_value,
                stamped_at=_at(TODAY) if status == "stamped" else None,
                idempotency_key=f"complement-{folio}",
                request_fingerprint="f" * 64,
            )
        )

    complement(
        open_invoice,
        folio=3011,
        partiality=1,
        status="stamped",
        payment_form="03",
        amount_cents=60000,
        prior_balance_cents=116000,
        outstanding_balance_cents=56000,
        uuid_value=str(uuid4()),
    )
    complement(
        open_invoice,
        folio=3012,
        partiality=2,
        status="requested",
        payment_form="03",
        amount_cents=20000,
        prior_balance_cents=56000,
        outstanding_balance_cents=36000,
    )
    complement(
        open_invoice,
        folio=3013,
        partiality=3,
        status="failed",
        payment_form="04",
        amount_cents=10000,
        prior_balance_cents=56000,
        outstanding_balance_cents=46000,
    )
    complement(
        paid_invoice,
        folio=3021,
        partiality=1,
        status="stamped",
        payment_form="03",
        amount_cents=50000,
        prior_balance_cents=50000,
        outstanding_balance_cents=0,
        uuid_value=str(uuid4()),
    )
    session.commit()


def test_revenue_reports_ppd_receivables_snapshot() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        _seed_ppd_receivables(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            revenue = client.get(
                "/admin/reports/revenue", headers=manager, params=PERIOD_PARAMS
            ).json()
            ppd = revenue["ppd_receivables"]
            assert ppd["as_of"] == club_date(datetime.now(timezone.utc)).isoformat()
            # Only the invoice with a remaining balance belongs to the cartera;
            # the fully collected one is excluded even though it was stamped.
            assert ppd["invoices"] == 1
            assert ppd["total_cents"] == 116000
            assert ppd["paid_cents"] == 60000
            assert ppd["outstanding_cents"] == 56000
            assert ppd["aging"] == {
                "current_cents": 0,
                "days_31_60_cents": 56000,
                "days_61_90_cents": 0,
                "over_90_cents": 0,
            }
            assert ppd["oldest_stamped_at"].startswith(
                (TODAY - timedelta(days=45)).isoformat()
            )
            assert ppd["stamped_complements"] == 1
            assert ppd["stamped_complement_cents"] == 60000
            assert ppd["requested_complements"] == 1
            assert ppd["requested_complement_cents"] == 20000
            assert ppd["failed_complements"] == 1
            assert ppd["failed_complement_cents"] == 10000

            # The cartera is a snapshot at the current cut-off, so changing the
            # report period must not change it.
            other = client.get(
                "/admin/reports/revenue",
                headers=manager,
                params={"date_from": OUTSIDE.isoformat(), "date_to": OUTSIDE.isoformat()},
            ).json()
            assert other["ppd_receivables"] == ppd
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_revenue_nets_refunds_by_period() -> None:
    """Counter money is net of refunds, counted in the period the refund was paid.

    A partially refunded sale keeps only the money that was not returned; a fully
    refunded sale nets to zero instead of vanishing from the gross; and a refund
    paid this period for a sale made outside it still lowers this period's money.
    """

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        beverage = Product(sku="AGUA", name="Agua", category="Bebidas", price_cents=1000)
        supplement = Product(sku="PROT", name="Proteína", category="Suplementos", price_cents=10000)
        session.add_all([beverage, supplement])
        session.flush()

        def _sale(
            folio: str, *, total: int, method: str, day: date, item: tuple, status: str = "completed"
        ) -> tuple[Sale, SaleItem]:
            sale = Sale(
                folio=folio,
                subtotal_cents=total,
                total_cents=total,
                payment_method=method,
                status=status,
                sold_at=_at(day),
            )
            session.add(sale)
            session.flush()
            product, quantity, unit_price = item
            line = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=quantity,
                unit_price_cents=unit_price,
                line_total_cents=quantity * unit_price,
            )
            session.add(line)
            session.flush()
            return sale, line

        def _return(
            folio: str, line: SaleItem, *, quantity: int, method: str, day: date, disposition: str = "restock"
        ) -> None:
            amount = quantity * line.unit_price_cents
            refund = SaleReturn(
                folio=folio,
                sale_id=line.sale_id,
                refund_method=method,
                total_refund_cents=amount,
                reason="Devolución de prueba",
                returned_at=_at(day),
            )
            session.add(refund)
            session.flush()
            session.add(
                SaleReturnItem(
                    return_id=refund.id,
                    sale_item_id=line.id,
                    product_id=line.product_id,
                    product_name=line.product_name,
                    sku=line.sku,
                    quantity=quantity,
                    unit_price_cents=line.unit_price_cents,
                    line_refund_cents=amount,
                    disposition=disposition,
                )
            )
            session.flush()

        _, partial_line = _sale("V-101", total=10000, method="cash", day=TODAY - timedelta(days=3), item=(beverage, 10, 1000))
        _return("D-101", partial_line, quantity=4, method="cash", day=TODAY - timedelta(days=1))
        _, full_line = _sale(
            "V-102", total=30000, method="card", day=TODAY, item=(supplement, 3, 10000), status="refunded"
        )
        _return("D-102", full_line, quantity=3, method="card", day=TODAY)
        _, outside_line = _sale("V-900", total=5000, method="cash", day=OUTSIDE, item=(beverage, 5, 1000))
        _return("D-900", outside_line, quantity=5, method="cash", day=TODAY)
        session.commit()

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")

            params = {"date_from": PERIOD_FROM.isoformat(), "date_to": PERIOD_TO.isoformat()}
            revenue = client.get("/admin/reports/revenue", headers=manager, params=params).json()

            # Gross is every sale rung up in the period (the outside sale does not
            # count); refunds are netted on a cash basis, so the outside sale's
            # refund paid today still subtracts here.
            assert revenue["sales_count"] == 2
            assert revenue["pos_gross_cents"] == 40000
            assert revenue["refunds_count"] == 3
            assert revenue["refunds_cents"] == 39000
            assert revenue["pos_cents"] == 1000  # 40000 - 39000
            assert revenue["average_ticket_cents"] == 20000  # gross / sales

            assert {row["label"]: row["amount_cents"] for row in revenue["pos_by_method"]} == {
                "cash": 1000,
                "card": 0,
            }
            assert {row["label"]: row["amount_cents"] for row in revenue["by_category"]} == {
                "Bebidas": 1000,
                "Suplementos": 0,
            }
            assert [(row["sku"], row["quantity"], row["amount_cents"]) for row in revenue["top_products"]] == [
                ("AGUA", 1, 1000)
            ]

            # The daily series nets per day, so a refund-heavy day can go negative,
            # and it still adds up to the headline figure.
            days = {day["day"]: day for day in revenue["by_day"]}
            assert days[(TODAY - timedelta(days=3)).isoformat()]["pos_cents"] == 10000
            assert days[(TODAY - timedelta(days=1)).isoformat()]["pos_cents"] == -4000
            assert days[TODAY.isoformat()]["refunds_cents"] == 35000
            assert days[TODAY.isoformat()]["pos_cents"] == -5000
            assert sum(day["pos_cents"] for day in revenue["by_day"]) == revenue["pos_cents"]

            overview = client.get("/admin/reports/overview", headers=manager, params=params).json()
            assert overview["pos_cents"] == 1000
            assert overview["pos_gross_cents"] == 40000
            assert overview["refunds_cents"] == 39000
            assert overview["refunds_count"] == 3

            export = client.get(
                "/admin/reports/export", headers=manager, params={"report": "revenue", **params}
            )
            assert export.status_code == 200, export.text
            lines = export.text.strip().splitlines()
            assert lines[0] == "Fecha,Ventas,Mostrador (MXN),Devoluciones (MXN),Membresías (MXN),Total (MXN)"
            today_row = next(line for line in lines[1:] if line.startswith(TODAY.isoformat()))
            assert today_row == f"{TODAY.isoformat()},1,-50.00,350.00,0.00,-50.00"
    finally:
        app.dependency_overrides.clear()


def test_resolve_period_bounds_follow_the_club_calendar() -> None:
    """The window bounds are local midnight, not UTC midnight."""

    utc = resolve_period(date(2026, 10, 18), date(2026, 10, 18), timezone_name="UTC")
    assert utc.timezone_name == "UTC"
    assert utc.start_at == datetime(2026, 10, 18, tzinfo=timezone.utc)
    assert utc.end_at == datetime(2026, 10, 19, tzinfo=timezone.utc)

    # Mexico is UTC-6, so the local day starts six hours after UTC midnight.
    mexico = resolve_period(date(2026, 10, 18), date(2026, 10, 18), timezone_name="America/Mexico_City")
    assert mexico.timezone_name == "America/Mexico_City"
    assert mexico.start_at == datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)
    assert mexico.end_at == datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc)


def test_reports_group_by_the_club_local_day() -> None:
    """A local evening sale is not pushed to the next UTC day.

    ``America/Mexico_City`` is UTC-6, so a sale rung up at 20:00 local is already
    the next day in UTC. A report ending "today" must include it and group it
    under the local day, and an early-UTC sale must fall on the previous local
    day.
    """

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        # 20:00 on TODAY locally, already the next UTC day.
        evening = Sale(
            folio="V-EVENING",
            subtotal_cents=5000,
            total_cents=5000,
            payment_method="cash",
            status="completed",
            sold_at=datetime.combine(TODAY + timedelta(days=1), time(2), tzinfo=timezone.utc),
        )
        # 05:00 UTC earlier that same local day, i.e. 23:00 the previous local day.
        late_night = Sale(
            folio="V-LATENIGHT",
            subtotal_cents=3000,
            total_cents=3000,
            payment_method="cash",
            status="completed",
            sold_at=datetime.combine(TODAY, time(5), tzinfo=timezone.utc),
        )
        session.add_all([evening, late_night])
        session.commit()

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            params = {"date_from": (TODAY - timedelta(days=2)).isoformat(), "date_to": TODAY.isoformat()}
            revenue = client.get("/admin/reports/revenue", headers=manager, params=params).json()

            assert revenue["period"]["timezone"] == "America/Mexico_City"
            # Both sales belong to the window even though one is on the next UTC day.
            assert revenue["pos_cents"] == 8000
            days = {day["day"]: day for day in revenue["by_day"]}
            assert days[TODAY.isoformat()]["pos_cents"] == 5000  # the evening sale
            assert days[(TODAY - timedelta(days=1)).isoformat()]["pos_cents"] == 3000  # the late-night sale
            assert (TODAY + timedelta(days=1)).isoformat() not in days
    finally:
        app.dependency_overrides.clear()


def test_membership_report_states_and_recurring_value() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        _seed_dataset(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")

            report = client.get(
                "/admin/reports/memberships", headers=accountant, params=PERIOD_PARAMS
            ).json()
            assert report["members_total"] == 6
            assert {row["label"]: row["count"] for row in report["members_by_status"]} == {
                "active": 4,
                "inactive": 1,
                "pending": 1,
            }
            assert {row["label"]: row["count"] for row in report["memberships_by_status"]} == {
                "active": 4,
                "cancelled": 1,
                "frozen": 1,
            }
            assert report["new_members"] == 2
            # "Expiring soon" follows the same rule as the member directory:
            # any active membership ending within a week, day passes included.
            assert report["members_expiring"] == 2
            assert report["payments_cents"] == 90000
            assert report["payments_count"] == 2
            assert {row["label"]: row["count"] for row in report["events"]} == {
                "payment_confirmed": 1,
                "cancelled": 1,
            }

            plans = {row["name"]: row for row in report["by_plan"]}
            assert plans["Mensual"]["active_count"] == 2
            assert plans["Mensual"]["monthly_cents"] == 50000
            assert plans["Anual"]["active_count"] == 1
            assert plans["Anual"]["monthly_cents"] == round(549900 * 30 / 365)
            assert plans["Pase de día"]["recurring"] is False
            assert plans["Pase de día"]["monthly_cents"] == 0
            assert report["mrr_expected_cents"] == plans["Mensual"]["monthly_cents"] * 2 + plans["Anual"]["monthly_cents"]

            # Events are bucketed per day: one activation and one termination.
            event_day = next(day for day in report["events_by_day"] if day["activations"] or day["terminations"])
            assert event_day["activations"] == 1
            assert event_day["terminations"] == 1
    finally:
        app.dependency_overrides.clear()


def test_operations_and_maintenance_reports() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        _seed_dataset(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")

            operations = client.get(
                "/admin/reports/operations", headers=manager, params=PERIOD_PARAMS
            ).json()
            assert operations["access_total"] == 4
            assert operations["access_denied"] == 1
            assert operations["access_manual"] == 1
            assert operations["access_authorized"] == 3
            assert [(row["label"], row["count"]) for row in operations["access_by_hour"]] == [
                ("10", 2),
                ("11", 2),
            ]
            assert sum(day["total"] for day in operations["access_by_day"]) == 4
            assert operations["class_sessions"] == 1
            assert operations["class_capacity"] == 20
            assert operations["class_reserved"] == 1
            assert operations["class_attended"] == 3
            assert operations["class_no_show"] == 1
            assert operations["class_occupancy_percent"] == 20  # (1 reserved + 3 attended) / 20
            assert operations["workouts"] == 1
            assert operations["workout_minutes"] == 45
            assert operations["measurements"] == 1

            maintenance = client.get(
                "/admin/reports/maintenance", headers=manager, params=PERIOD_PARAMS
            ).json()
            assert maintenance["cost_cents"] == 10000
            assert maintenance["records_count"] == 1
            assert [(row["label"], row["amount_cents"]) for row in maintenance["by_kind"]] == [
                ("preventive", 10000)
            ]
            assert len(maintenance["by_equipment"]) == 1
            equipment = maintenance["by_equipment"][0]
            assert equipment["name"] == "Caminadora"
            assert equipment["cost_cents"] == 10000
            assert equipment["records_count"] == 1
            assert equipment["open_tickets"] == 1
            assert maintenance["tickets_created"] == 1
            assert {row["label"]: row["count"] for row in maintenance["tickets_by_severity"]} == {
                "critical": 1
            }
            assert {row["label"]: row["count"] for row in maintenance["equipment_by_status"]} == {
                "operational": 2
            }
            assert maintenance["preventives_due"] == 1
    finally:
        app.dependency_overrides.clear()


def test_report_period_validation_and_csv_export() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        _seed_dataset(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")

            # The window must be ordered and bounded.
            assert client.get(
                "/admin/reports/overview",
                headers=manager,
                params={"date_from": TODAY.isoformat(), "date_to": PERIOD_FROM.isoformat()},
            ).status_code == 422
            assert client.get(
                "/admin/reports/overview",
                headers=manager,
                params={"date_from": (TODAY - timedelta(days=800)).isoformat(), "date_to": TODAY.isoformat()},
            ).status_code == 422
            assert client.get(
                "/admin/reports/overview",
                headers=manager,
                params={"date_from": "no-es-fecha"},
            ).status_code == 422

            # Only the known reports can be exported.
            assert client.get(
                "/admin/reports/export",
                headers=manager,
                params={"report": "inventado", **PERIOD_PARAMS},
            ).status_code == 404

            response = client.get(
                "/admin/reports/export", headers=manager, params={"report": "revenue", **PERIOD_PARAMS}
            )
            assert response.status_code == 200, response.text
            assert response.headers["content-type"].startswith("text/csv")
            assert "attachment" in response.headers["content-disposition"]
            lines = response.text.strip().splitlines()
            assert lines[0] == "Fecha,Ventas,Mostrador (MXN),Devoluciones (MXN),Membresías (MXN),Total (MXN)"
            assert len(lines) == 15 + 1  # one row per day in the window
            closing = {line.split(",")[0]: line.split(",") for line in lines[1:]}
            assert closing[TODAY.isoformat()] == [TODAY.isoformat(), "1", "200.00", "0.00", "0.00", "200.00"]

            # A missing report name falls back to the overview export.
            default = client.get(
                "/admin/reports/export", headers=manager, params=PERIOD_PARAMS
            )
            assert default.status_code == 200
            assert default.text.startswith("Indicador,Valor")
            assert f"reporte-overview-{PERIOD_FROM.isoformat()}-{PERIOD_TO.isoformat()}.csv" in default.headers[
                "content-disposition"
            ]
    finally:
        app.dependency_overrides.clear()


def test_inventory_report_valuates_stock_and_purchases() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        _seed_dataset(session)

        beverage = session.exec(select(Product).where(Product.sku == "AGUA")).one()
        supplement = session.exec(select(Product).where(Product.sku == "PROT")).one()

        # Current balances: Agua sits at its minimum (low) and Proteína is at zero
        # (out). Valuation reads these balances, not the movement ledger.
        session.add_all(
            [
                InventoryStock(product_id=beverage.id, quantity=4),
                InventoryStock(product_id=supplement.id, quantity=0),
            ]
        )

        # Ledger: three movements inside the window and a decoy two months back.
        session.add_all(
            [
                InventoryMovement(
                    product_id=beverage.id,
                    movement_type="intake",
                    quantity=6,
                    reference_type="purchase_order",
                    occurred_at=_at(TODAY - timedelta(days=3)),
                ),
                InventoryMovement(
                    product_id=beverage.id,
                    movement_type="sale",
                    quantity=-2,
                    occurred_at=_at(TODAY - timedelta(days=1)),
                ),
                InventoryMovement(
                    product_id=supplement.id,
                    movement_type="adjustment",
                    quantity=-1,
                    occurred_at=_at(TODAY),
                ),
                InventoryMovement(
                    product_id=beverage.id,
                    movement_type="waste",
                    quantity=-3,
                    occurred_at=_at(OUTSIDE),
                ),
            ]
        )

        supplier = Supplier(name="Distribuidora Norte")
        dormant = Supplier(name="Proveedor Inactivo", is_active=False)
        session.add_all([supplier, dormant])
        session.flush()

        received = PurchaseOrder(
            folio="OC-1",
            supplier_id=supplier.id,
            status="received",
            subtotal_cents=5000,
            tax_cents=0,
            total_cents=5000,
            created_at=_at(TODAY - timedelta(days=4)),
            received_at=_at(TODAY - timedelta(days=2)),
        )
        open_order = PurchaseOrder(
            folio="OC-2",
            supplier_id=supplier.id,
            status="created",
            subtotal_cents=3000,
            tax_cents=0,
            total_cents=3000,
            created_at=_at(TODAY - timedelta(days=1)),
        )
        cancelled = PurchaseOrder(
            folio="OC-3",
            supplier_id=supplier.id,
            status="cancelled",
            subtotal_cents=9999,
            tax_cents=0,
            total_cents=9999,
            created_at=_at(TODAY - timedelta(days=1)),
        )
        old_order = PurchaseOrder(
            folio="OC-4",
            supplier_id=supplier.id,
            status="received",
            subtotal_cents=7777,
            tax_cents=0,
            total_cents=7777,
            created_at=_at(OUTSIDE),
            received_at=_at(OUTSIDE),
        )
        session.add_all([received, open_order, cancelled, old_order])
        session.flush()
        session.add(
            PurchaseOrderItem(
                purchase_order_id=received.id,
                product_id=beverage.id,
                product_name=beverage.name,
                sku=beverage.sku,
                quantity=6,
                received_quantity=6,
                unit_cost_cents=400,
                line_total_cents=2400,
            )
        )
        session.commit()

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")

            report = client.get(
                "/admin/reports/inventory", headers=manager, params=PERIOD_PARAMS
            )
            assert report.status_code == 200, report.text
            payload = report.json()

            # Valuation is a snapshot of the current balances.
            assert payload["products_total"] == 2
            assert payload["products_active"] == 2
            assert payload["products_inactive"] == 0
            assert payload["stock_units"] == 4
            assert payload["stock_value_cents"] == 1600  # 4 * 4.00
            assert payload["retail_value_cents"] == 4000  # 4 * 10.00
            assert payload["low_stock"] == 1  # Agua at its minimum, still above zero
            assert payload["out_of_stock"] == 1  # Proteína at zero
            assert {
                row["label"]: (row["count"], row["amount_cents"]) for row in payload["by_category"]
            } == {"Bebidas": (4, 1600), "Suplementos": (0, 0)}
            assert [row["sku"] for row in payload["by_product"]] == ["AGUA", "PROT"]

            # The period bounds the ledger; the waste two months back is ignored.
            assert payload["movements_count"] == 3
            assert payload["units_in"] == 6
            assert payload["units_out"] == 3  # 2 sold + 1 adjusted away
            assert {
                row["label"]: (row["movements"], row["units"])
                for row in payload["movements_by_type"]
            } == {"intake": (1, 6), "sale": (1, -2), "adjustment": (1, -1)}

            # Purchases created in the period, minus the cancelled one; a receipt
            # counts by its received_at, so the old one stays out.
            assert payload["orders_created"] == 3
            assert {row["label"]: row["count"] for row in payload["orders_by_status"]} == {
                "received": 1,
                "created": 1,
                "cancelled": 1,
            }
            assert payload["orders_value_cents"] == 8000
            assert payload["orders_received"] == 1
            assert payload["orders_received_value_cents"] == 5000
            assert payload["suppliers_total"] == 2
            assert payload["suppliers_active"] == 1
            assert payload["open_orders"] == 1
            assert payload["open_orders_value_cents"] == 3000
            assert [
                (row["label"], row["count"], row["amount_cents"]) for row in payload["by_supplier"]
            ] == [("Distribuidora Norte", 2, 8000)]

            export = client.get(
                "/admin/reports/export",
                headers=manager,
                params={"report": "inventory", **PERIOD_PARAMS},
            )
            assert export.status_code == 200, export.text
            assert export.text.splitlines()[0].startswith("Producto,SKU,Categoría,Existencia")
            assert "Agua 600ml,AGUA,Bebidas,4,4.00,10.00,16.00,40.00" in export.text
    finally:
        app.dependency_overrides.clear()
