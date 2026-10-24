"""Seed the preview database with demo member accounts (sales on account + payments).

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_member_accounts.py

The script is idempotent per member: it only seeds active members that have no
account activity yet (no sale on account), so running it again never duplicates
data or touches accounts that already exist. It goes through the module service so
the inventory ledger, the register link and the computed balance behave exactly as
in production. Sales and account payments require an open register shift, so the
script opens one (with a zero float) when the last seeded shift is closed.

Three scenarios are seeded, one per member, so the «Cuentas por cobrar» tab shows
real variety: a charge with a partial payment, a charge reduced by a return, and a
charge that is still fully outstanding.
"""

import sys

sys.path.insert(0, r".\src")

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.modules import (  # noqa: E402,F401
    access,
    classes,
    identity,
    inventory,
    maintenance,
    memberships,
    reports,
    routines,
    staffing,
)
from app.modules.identity.models import AppUser  # noqa: E402
from app.modules.identity.service import ensure_default_access_control  # noqa: E402
from app.modules.inventory import service as inventory_service  # noqa: E402
from app.modules.inventory.models import Sale, SaleItem  # noqa: E402
from app.modules.memberships.models import Member  # noqa: E402

DATABASE_URL = "sqlite:///./gym_preview.db"


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_default_access_control(session)

        charged_member_ids = {
            row.member_id
            for row in session.exec(
                select(Sale).where(Sale.payment_method == "account")
            ).all()
        }
        if len(charged_member_ids) >= 3:
            print("Member accounts already seeded; skipping.")
            return
        members = [
            member
            for member in session.exec(
                select(Member).where(Member.status == "active").order_by(Member.first_name)
            ).all()
            if member.id not in charged_member_ids
        ]
        products = [
            item
            for item in inventory_service.list_products(session, page=1, page_size=100).items
            if item.is_active and item.stock >= 3
        ]
        if not members or not products:
            print("No hay socios activos o productos con stock suficientes; se omite el seed.")
            return

        admin = session.exec(select(AppUser).order_by(AppUser.email)).first()
        actor_id = admin.id if admin is not None else None

        if inventory_service.current_cash_session(session) is None:
            inventory_service.open_cash_session(session, opening_cash_cents=0, actor_id=actor_id)
            print("Turno de caja abierto para registrar las cuentas demo.")

        def charge(member: Member, product, quantity: int) -> object:
            return inventory_service.register_sale(
                session,
                items=[(product.id, quantity)],
                payment_method="account",
                member_id=member.id,
                note="Consumo cargado a la cuenta del socio",
                cashier_id=actor_id,
            )

        # 1) Charge with a partial payment: the member still owes half.
        member = members[0]
        sale = charge(member, products[0], 2)
        inventory_service.register_member_account_payment(
            session,
            member.id,
            amount_cents=sale.total_cents // 2,
            method="cash",
            note="Abono parcial en mostrador",
            actor_id=actor_id,
        )
        print(f"{member.first_name} {member.last_name}: venta {sale.folio} con abono parcial.")

        # 2) Charge reduced by a return: one unit goes back and credits the account.
        if len(members) > 1 and len(products) > 1:
            member = members[1]
            sale = charge(member, products[1], 2)
            line = session.exec(select(SaleItem).where(SaleItem.sale_id == sale.id)).first()
            if line is not None:
                inventory_service.register_sale_return(
                    session,
                    sale.id,
                    lines=[(line.id, 1, "restock")],
                    reason="Talla equivocada; el importe se abona a la cuenta",
                    refund_method="account",
                    actor_id=actor_id,
                )
            print(f"{member.first_name} {member.last_name}: venta {sale.folio} con devolución abonada.")

        # 3) Charge still fully outstanding.
        if len(members) > 2:
            member = members[2]
            sale = charge(member, products[2 % len(products)], 1)
            print(f"{member.first_name} {member.last_name}: venta {sale.folio} sin abono.")

        directory = inventory_service.list_member_accounts(session, page=1, page_size=10)
        for item in directory.items:
            print(f"  Saldo de {item.member_name}: {item.balance_cents} centavos")
        print(f"Total por cobrar: {directory.total_receivable_cents} centavos")
        print("Done!")


if __name__ == "__main__":
    main()
