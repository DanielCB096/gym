"""Seed the preview database with a couple of realistic sale returns.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_returns.py

The script is idempotent: it does nothing when the ``sale_returns`` table already
has rows. It goes through the module service so the inventory ledger, the cash
session link and the full-refund sale status behave exactly as in production.
Returns require an open register shift, so the script opens one (with a zero
float) when the last seeded shift is already closed.
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
from app.modules.inventory.models import Sale, SaleItem, SaleReturn  # noqa: E402

DATABASE_URL = "sqlite:///./gym_preview.db"


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_default_access_control(session)

        if session.exec(select(SaleReturn)).first() is not None:
            print("Sale returns already seeded; skipping.")
            return

        admin = session.exec(select(AppUser).order_by(AppUser.email)).first()
        actor_id = admin.id if admin is not None else None

        # Returns are tied to the shift that pays them, so make sure one is open.
        if inventory_service.current_cash_session(session) is None:
            inventory_service.open_cash_session(session, opening_cash_cents=0, actor_id=actor_id)
            print("Turno de caja abierto para registrar las devoluciones demo.")

        sales = session.exec(
            select(Sale).where(Sale.status == "completed").order_by(Sale.sold_at.desc()).limit(50)
        ).all()
        if len(sales) < 2:
            print("Se necesitan al menos dos ventas para sembrar devoluciones; se omite.")
            return

        first, second = sales[0], sales[1]
        first_items = session.exec(select(SaleItem).where(SaleItem.sale_id == first.id)).all()
        second_items = session.exec(select(SaleItem).where(SaleItem.sale_id == second.id)).all()
        if not first_items or not second_items:
            print("Las ventas elegidas no tienen líneas; se omite el seed.")
            return

        # One unit of the priciest line goes back to the shelf (partial refund).
        line_a = max(first_items, key=lambda item: item.unit_price_cents)
        returned_a = inventory_service.register_sale_return(
            session,
            first.id,
            lines=[(line_a.id, 1, "restock")],
            reason="Cambio de talla; el producto vuelve al inventario",
            refund_method="cash",
            actor_id=actor_id,
        )

        # One unit of another sale is received and discarded as shrinkage.
        line_b = max(second_items, key=lambda item: item.unit_price_cents)
        returned_b = inventory_service.register_sale_return(
            session,
            second.id,
            lines=[(line_b.id, 1, "write_off")],
            reason="Producto dañado por el cliente; no es revendible",
            refund_method=second.payment_method,
            actor_id=actor_id,
        )

        directory = inventory_service.list_sale_returns(session, page=1, page_size=10)
        print(f"Devolución {returned_a.folio} (venta {first.folio}): reingreso a stock.")
        print(f"Devolución {returned_b.folio} (venta {second.folio}): merma por producto dañado.")
        print(f"Devoluciones registradas: {directory.total} · total {directory.summary.total_refund_cents} centavos")
        print("Done!")


if __name__ == "__main__":
    main()
