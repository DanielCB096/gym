"""Seed the preview database with bank accounts and statement lines.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_reconciliation.py

The script is idempotent: it does nothing when a bank account already exists.
It imports the statement through the finance service (so the deterministic
duplicate hash and the event trail behave as in production), then links a few
lines to real electronic payments and sales from the preview data:

* an exact membership payment match (reconciled),
* an exact sale match (reconciled),
* a sale match with a bank fee difference (difference),
* a deposit marked for review,
* pending lines with and without suggestions.

All money stays in the existing payment/sale rows; the bank line only points at
them.
"""

import sys
from datetime import timedelta
from uuid import UUID

sys.path.insert(0, r".\src")

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.modules import (  # noqa: E402,F401
    access,
    billing,
    classes,
    finance,
    identity,
    inventory,
    maintenance,
    memberships,
    reports,
    routines,
    staffing,
)
from app.modules.finance.models import BankAccount, BankMovement, utc_now  # noqa: E402
from app.modules.finance.service import (  # noqa: E402
    create_bank_account,
    flag_bank_movement,
    import_bank_movements,
    list_bank_movements,
    match_bank_movement,
)
from app.modules.identity.models import AppUser  # noqa: E402
from app.modules.identity.service import ensure_default_access_control  # noqa: E402
from app.modules.inventory.models import Sale  # noqa: E402
from app.modules.memberships.models import Member, Membership, Payment, Plan  # noqa: E402
from app.timezone import club_date  # noqa: E402

DATABASE_URL = "sqlite:///./gym_preview.db"


def _movement(
    session: Session, account_id: UUID, reference: str
) -> BankMovement | None:
    return session.exec(
        select(BankMovement).where(
            BankMovement.bank_account_id == account_id,
            BankMovement.reference == reference,
        )
    ).first()


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_default_access_control(session)

        if session.exec(select(BankAccount)).first() is not None:
            print("Las cuentas bancarias ya están sembradas; se omite.")
            return

        accountant = session.exec(
            select(AppUser).where(AppUser.email == "accountant@example.com")
        ).first()
        admin = accountant or session.exec(select(AppUser).order_by(AppUser.email)).first()
        actor_id = admin.id if admin is not None else None

        payment_rows = session.exec(
            select(Payment, Member, Plan)
            .join(Member, Payment.member_id == Member.id)
            .join(Membership, Payment.membership_id == Membership.id)
            .join(Plan, Membership.plan_id == Plan.id)
            .where(
                Payment.currency == "MXN",
                Payment.method.in_(("card", "transfer", "spei")),
            )
            .order_by(Payment.paid_at.desc())
            .limit(4)
        ).all()
        sale_rows = session.exec(
            select(Sale)
            .where(
                Sale.status == "completed",
                Sale.payment_method.in_(("card", "transfer")),
                Sale.total_cents > 100,
            )
            .order_by(Sale.sold_at.desc())
            .limit(4)
        ).all()
        if len(payment_rows) < 2 or len(sale_rows) < 2:
            print("Se necesitan dos cobros electrónicos y dos ventas con tarjeta/transferencia; se omite.")
            return

        exact_payment, exact_member, exact_plan = payment_rows[0]
        pending_payment, pending_member, pending_plan = payment_rows[1]
        exact_sale = sale_rows[0]
        difference_sale = sale_rows[1]

        today = club_date(utc_now())
        payment_exact_reference = f"TRF-{str(exact_payment.id)[:8].upper()}"
        payment_pending_reference = f"SPEI-{str(pending_payment.id)[:8].upper()}"
        sale_difference_reference = f"TRF-{difference_sale.folio}"
        sale_exact_reference = f"TRF-{exact_sale.folio}"

        operating = create_bank_account(
            session,
            name="Cuenta operativa",
            bank_name="BBVA",
            account_last4="4821",
            currency="MXN",
            actor_id=actor_id,
        )
        reserve = create_bank_account(
            session,
            name="Cuenta de reservas",
            bank_name="Banorte",
            account_last4="7310",
            currency="MXN",
            actor_id=actor_id,
        )
        operating_id = UUID(str(operating["id"]))
        reserve_id = UUID(str(reserve["id"]))

        difference_cents = difference_sale.total_cents - 500
        if difference_cents <= 0:
            difference_cents = difference_sale.total_cents

        operating_rows = [
            {
                "occurred_on": club_date(exact_payment.paid_at),
                "amount_cents": exact_payment.amount_cents,
                "reference": payment_exact_reference,
                "description": (
                    f"Pago membresía {exact_member.first_name} {exact_member.last_name}"
                    f" · {exact_plan.name}"
                ),
            },
            {
                "occurred_on": club_date(pending_payment.paid_at),
                "amount_cents": pending_payment.amount_cents,
                "reference": payment_pending_reference,
                "description": (
                    f"Pago membresía {pending_member.first_name} {pending_member.last_name}"
                    f" · {pending_plan.name}"
                ),
            },
            {
                "occurred_on": club_date(difference_sale.sold_at),
                "amount_cents": difference_cents,
                "reference": sale_difference_reference,
                "description": f"Depósito venta {difference_sale.folio}",
            },
            {
                "occurred_on": today - timedelta(days=2),
                "amount_cents": -45000,
                "reference": "COMISION-MANEJO",
                "description": "Comisión mensual de manejo de cuenta",
            },
            {
                "occurred_on": today - timedelta(days=1),
                "amount_cents": 250000,
                "reference": "DEPOSITO-SUCURSAL",
                "description": "Depósito en sucursal por identificar",
            },
        ]
        reserve_rows = [
            {
                "occurred_on": club_date(exact_sale.sold_at),
                "amount_cents": exact_sale.total_cents,
                "reference": sale_exact_reference,
                "description": f"Depósito venta {exact_sale.folio}",
            },
            {
                "occurred_on": today - timedelta(days=1),
                "amount_cents": 90000,
                "reference": "DEPOSITO-EFECTIVO",
                "description": "Depósito en efectivo por identificar",
            },
        ]

        operating_result = import_bank_movements(
            session, operating_id, operating_rows, actor_id=actor_id
        )
        reserve_result = import_bank_movements(
            session, reserve_id, reserve_rows, actor_id=actor_id
        )
        print(
            f"Importados {operating_result['imported']} movimientos en la cuenta operativa y "
            f"{reserve_result['imported']} en la cuenta de reservas."
        )

        exact_payment_line = _movement(session, operating_id, payment_exact_reference)
        difference_line = _movement(session, operating_id, sale_difference_reference)
        exact_sale_line = _movement(session, reserve_id, sale_exact_reference)
        review_line = _movement(session, reserve_id, "DEPOSITO-EFECTIVO")
        if None in (exact_payment_line, difference_line, exact_sale_line, review_line):
            print("No se encontraron las líneas recién importadas; se omite la conciliación.")
            return

        match_bank_movement(
            session,
            exact_payment_line.id,
            source="membership_payment",
            source_id=exact_payment.id,
            actor_id=actor_id,
        )
        match_bank_movement(
            session,
            exact_sale_line.id,
            source="sale",
            source_id=exact_sale.id,
            actor_id=actor_id,
        )
        match_bank_movement(
            session,
            difference_line.id,
            source="sale",
            source_id=difference_sale.id,
            note="Comisión bancaria descontada por el banco (vista previa).",
            actor_id=actor_id,
        )
        flag_bank_movement(
            session,
            review_line.id,
            status="reviewing",
            note="Depósito sin referencia; revisar con el comprobante del socio.",
            actor_id=actor_id,
        )

        summary = list_bank_movements(session, page=1, page_size=50)["summary"]
        print(
            f"Conciliación: {summary['count']} movimientos · "
            f"{summary['pending']} pendientes · {summary['difference']} con diferencia · "
            f"{summary['reviewing']} en revisión · {summary['reconciled']} conciliados."
        )
        print("Done!")


if __name__ == "__main__":
    main()
