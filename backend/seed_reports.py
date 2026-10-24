"""Backdate a demo history so the reports module has something to chart.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_reports.py

The reports module only aggregates rows other modules already wrote, so a
window with everything clustered on a single day draws flat charts. This script
walks the last month and writes:

* one cash shift per past day with a handful of counter sales, through the
  inventory service so stock, folios and shift totals behave as in production;
* access events with a plausible morning/evening traffic curve;
* membership payments and membership events spread across the window.

Each block is idempotent on its own: it skips when rows older than a week
already exist.
"""

import sys

sys.path.insert(0, r".\src")

import random  # noqa: E402
from datetime import date, datetime, time, timedelta, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.modules import (  # noqa: E402,F401
    access,
    classes,
    identity,
    inventory,
    maintenance,
    memberships,
    routines,
    staffing,
)
from app.modules.access.models import AccessEvent  # noqa: E402
from app.modules.identity.models import AppUser  # noqa: E402
from app.modules.identity.service import ensure_default_access_control  # noqa: E402
from app.modules.inventory import service as inventory_service  # noqa: E402
from app.modules.inventory.models import Product, Sale  # noqa: E402
from app.modules.memberships.models import (  # noqa: E402
    Member,
    Membership,
    MembershipEvent,
    Payment,
    PaymentAttempt,
    PaymentMethod,
    Plan,
)

DATABASE_URL = "sqlite:///./gym_preview.db"
DAYS = 30
OPENING_CASH_CENTS = 50000
SEEDED_AFTER_DAYS = 8

# Reader-shaped traffic: mostly mornings and evenings.
HOUR_WEIGHTS = {
    6: 3,
    7: 6,
    8: 8,
    9: 6,
    10: 4,
    11: 3,
    12: 4,
    13: 3,
    14: 3,
    15: 4,
    16: 5,
    17: 7,
    18: 9,
    19: 8,
    20: 5,
    21: 2,
}
# Monday = 0, Sunday = 6.
WEEKDAY_FACTORS = (0.95, 1.1, 1.05, 1.0, 0.85, 0.7, 0.5)

# product sku -> relative popularity in the shop.
PRODUCT_WEIGHTS = {
    "AGUA-600": 26,
    "GATORADE-600": 16,
    "ELECTROLIT": 12,
    "BARRA-PRO": 14,
    "PROT-1K": 7,
    "CREATINA-300": 5,
    "SHAKER-700": 8,
    "TOALLA-MF": 5,
    "GUANTES-M": 3,
    "CANDADO-COM": 2,
    "11011": 4,
}
READERS = ("TURN-1", "TURN-2")
READER_HOURS = list(HOUR_WEIGHTS)
READER_WEIGHTS = [HOUR_WEIGHTS[hour] for hour in READER_HOURS]


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=minute), tzinfo=timezone.utc)


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)
    random.seed(20261017)

    with Session(engine) as session:
        ensure_default_access_control(session)

        today = date.today()
        cutoff = _at(today - timedelta(days=SEEDED_AFTER_DAYS), 0)
        admin = session.exec(select(AppUser).order_by(AppUser.email)).first()
        actor_id = admin.id if admin is not None else None

        members = session.exec(select(Member)).all()
        member_ids = [member.id for member in members]

        products = session.exec(select(Product).where(Product.is_active == True)).all()  # noqa: E712
        products_by_sku = {product.sku: product for product in products}

        seeded_sales = session.exec(select(Sale).where(Sale.sold_at < cutoff)).first() is not None
        seeded_access = (
            session.exec(select(AccessEvent).where(AccessEvent.occurred_at < cutoff)).first()
            is not None
        )
        seeded_payments = (
            session.exec(select(Payment).where(Payment.paid_at < cutoff)).first() is not None
        )

        # --- Counter sales: one shift per past day -------------------------
        if seeded_sales:
            print("Ventas ya tienen historia; se omite el mostrador.")
        else:
            # Top up stock first: a month of demo sales would otherwise drain
            # the products seeded for the shop.
            for product in products:
                inventory_service.register_stock_movement(
                    session,
                    product.id,
                    movement_type="intake",
                    quantity=80,
                    reason="Carga inicial para el demo de reportes",
                    actor_id=actor_id,
                    now=_at(today - timedelta(days=DAYS), 7),
                )
            session.commit()

            open_shift = inventory_service.current_cash_session(session)
            if open_shift is not None:
                inventory_service.close_cash_session(
                    session,
                    open_shift.id,
                    counted_cash_cents=open_shift.expected_cash_cents,
                    actor_id=actor_id,
                    now=_at(today, 7, 30),
                )

            menu = [sku for sku, weight in PRODUCT_WEIGHTS.items() for _ in range(weight)]

            def _sell(day: date, sales_count: int) -> None:
                for _ in range(sales_count):
                    picks = random.sample(menu, k=random.randint(1, 3))
                    items = []
                    seen: set[str] = set()
                    for sku in picks:
                        if sku in seen:
                            continue
                        seen.add(sku)
                        product = products_by_sku.get(sku)
                        if product is not None:
                            items.append((product.id, random.choices([1, 2], weights=[82, 18])[0]))
                    if not items:
                        continue
                    method = random.choices(
                        ["cash", "card", "transfer"], weights=[55, 33, 12]
                    )[0]
                    hour = random.choice([9, 10, 11, 12, 13, 16, 17, 18, 19, 20])
                    inventory_service.register_sale(
                        session,
                        items=items,
                        payment_method=method,
                        member_id=random.choice(member_ids) if member_ids and random.random() < 0.3 else None,
                        cashier_id=actor_id,
                        now=_at(day, hour, random.choice([5, 15, 25, 35, 45, 55])),
                    )

            for offset in range(DAYS, 0, -1):
                day = today - timedelta(days=offset)
                factor = WEEKDAY_FACTORS[day.weekday()]
                inventory_service.open_cash_session(
                    session,
                    opening_cash_cents=OPENING_CASH_CENTS,
                    actor_id=actor_id,
                    now=_at(day, 8),
                )
                _sell(day, max(2, round(random.uniform(2, 5) * factor)))
                shift = inventory_service.current_cash_session(session)
                if shift is not None:
                    # Most days balance; a couple of days carry a small,
                    # explained difference so the caja report is not flat.
                    intentional = offset in (7, 15, 23)
                    delta = random.choice([-2500, -1500, 1500]) if intentional else 0
                    inventory_service.close_cash_session(
                        session,
                        shift.id,
                        counted_cash_cents=shift.expected_cash_cents + delta,
                        notes="Faltante de cambio en caja" if delta < 0 else (
                            "Sobrante por propina" if delta > 0 else None
                        ),
                        actor_id=actor_id,
                        now=_at(day, 20),
                    )

            # Leave a fresh shift open today so the point of sale stays usable.
            inventory_service.open_cash_session(
                session,
                opening_cash_cents=OPENING_CASH_CENTS,
                actor_id=actor_id,
                now=_at(today, 8),
            )
            _sell(today, 4)
            session.commit()
            print("Mostrador con historia de 30 días listo.")

        # --- Access events -------------------------------------------------
        if seeded_access:
            print("Accesos ya tienen historia; se omite el control de acceso.")
        else:
            for offset in range(DAYS - 1, -1, -1):
                day = today - timedelta(days=offset)
                factor = WEEKDAY_FACTORS[day.weekday()]
                entries = max(3, round(14 * factor))
                for _ in range(entries):
                    hour = random.choices(READER_HOURS, weights=READER_WEIGHTS)[0]
                    authorized = random.random() > 0.07
                    manual = random.random() < 0.1
                    member_id = random.choice(member_ids) if member_ids and random.random() < 0.9 else None
                    session.add(
                        AccessEvent(
                            event_id=uuid4(),
                            member_id=member_id,
                            reader_id=random.choice(READERS),
                            direction="entry",
                            authorized=authorized,
                            reason="entry_allowed" if authorized else "membership_not_active",
                            source="manual" if manual else "reader",
                            occurred_at=_at(day, hour, random.choice([0, 10, 20, 30, 40, 50])),
                        )
                    )
                    if authorized and hour < 21:
                        session.add(
                            AccessEvent(
                                event_id=uuid4(),
                                member_id=member_id,
                                reader_id=random.choice(READERS),
                                direction="exit",
                                authorized=True,
                                reason="exit_registered",
                                source="reader",
                                occurred_at=_at(day, hour + 1, random.choice([5, 25, 45])),
                            )
                        )
            session.commit()
            print("Accesos de 30 días listos.")

        # --- Membership payments and events --------------------------------
        if seeded_payments:
            print("Cobros de membresía ya tienen historia; se omite el bloque.")
        else:
            card_method = session.exec(
                select(PaymentMethod).where(PaymentMethod.status == "active")
            ).first()
            active = session.exec(
                select(Membership).where(Membership.status == "active")
            ).all()
            counter = 0

            def _register_payment(membership: Membership, day: date, attempt_number: int) -> None:
                nonlocal counter
                counter += 1
                plan = session.get(Plan, membership.plan_id)
                amount = plan.price_cents if plan is not None else 39900
                method = ["cash", "card", "transfer"][counter % 3]
                if method == "card" and card_method is None:
                    method = "cash"
                attempt = PaymentAttempt(
                    membership_id=membership.id,
                    payment_method_id=card_method.id if method == "card" and card_method else None,
                    method=method,
                    idempotency_key=f"seed-reports-{membership.id}-{day.isoformat()}-{attempt_number}",
                    request_fingerprint=f"seed-{membership.id.hex[:12]}-{day.isoformat()}",
                    attempt_number=attempt_number,
                    amount_cents=amount,
                    status="succeeded",
                    due_at=_at(day, 10),
                    resolved_at=_at(day, 10, 5),
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
                        paid_at=_at(day, 10, 5),
                    )
                )
                session.add(
                    MembershipEvent(
                        membership_id=membership.id,
                        event_type="payment_confirmed",
                        actor_type="provider",
                        actor_id=actor_id,
                        occurred_at=_at(day, 10, 5),
                    )
                )

            for index, membership in enumerate(active):
                day = today - timedelta(days=max(1, 24 - index * 3))
                _register_payment(membership, day, 1)

            # A pair of renewals so the window shows repeat charges.
            for index in (0, 1):
                membership = active[index]
                _register_payment(membership, today - timedelta(days=4 - index), 2)

            # Closing events for the non-active memberships, when missing.
            for membership in session.exec(
                select(Membership).where(Membership.status.in_(["frozen", "cancelled"]))
            ).all():
                event_type = "frozen" if membership.status == "frozen" else "cancelled"
                exists = session.exec(
                    select(MembershipEvent).where(
                        MembershipEvent.membership_id == membership.id,
                        MembershipEvent.event_type == event_type,
                    )
                ).first()
                if exists is None:
                    session.add(
                        MembershipEvent(
                            membership_id=membership.id,
                            event_type=event_type,
                            actor_type="employee",
                            actor_id=actor_id,
                            occurred_at=_at(today - timedelta(days=6), 12),
                        )
                    )
            session.commit()
            print(f"Cobros de membresía listos ({counter} cobros en el periodo): {len(active)} socios activos.")

        print("Sembrado de reportes terminado.")


if __name__ == "__main__":
    main()
