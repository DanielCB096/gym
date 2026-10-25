"""Seed the preview database with a PPD invoice and its payment complements.

Run it from the ``backend`` directory after ``seed_billing.py``:

    .\\.venv\\Scripts\\python.exe seed_ppd.py

The script is idempotent: it does nothing when a PPD invoice already exists. It
uses the billing service, so the folios, sequential partialities, balance
recalculation and simulated PAC behave exactly as in production. The seeded
history leaves one stamped partiality, one cancelled complement (with its
trail) and one pending complement so the panel can exercise every action.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, r".\src")

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.modules import (  # noqa: E402,F401
    access,
    billing,
    classes,
    identity,
    inventory,
    maintenance,
    memberships,
    reports,
    routines,
    staffing,
)
from app.modules.billing import service as billing_service  # noqa: E402
from app.modules.billing.models import Invoice  # noqa: E402
from app.modules.identity.models import AppUser  # noqa: E402
from app.modules.identity.service import ensure_default_access_control  # noqa: E402
from app.timezone import club_date  # noqa: E402

DATABASE_URL = "sqlite:///./gym_preview.db"

PUBLIC_GENERAL = {
    "rfc": "XAXX010101000",
    "legal_name": "PÚBLICO EN GENERAL",
    "tax_regime": "616",
    "postal_code": "01000",
    "cfdi_use": "S01",
    "email": None,
}


def _receptor_for(origin) -> dict:
    if origin.member_id and origin.member_name:
        return {
            "rfc": "GARC850312AB1",
            "legal_name": origin.member_name,
            "tax_regime": "612",
            "postal_code": "06700",
            "cfdi_use": "G03",
            "email": "facturacion@example.com",
        }
    return dict(PUBLIC_GENERAL)


def main() -> None:
    os.environ.setdefault("PAC_PROVIDER", "simulated")

    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_default_access_control(session)

        existing = session.exec(
            select(Invoice).where(Invoice.payment_method == "PPD")
        ).first()
        if existing is not None:
            print("Las facturas PPD ya están sembradas; se omite.")
            return

        sales = billing_service.list_origin_options(
            session, origin_type="sale", page=1, page_size=20
        )
        payments = billing_service.list_origin_options(
            session, origin_type="membership_payment", page=1, page_size=20
        )
        candidates = [*sales.items, *payments.items]
        if not candidates:
            print(
                "No hay operaciones facturables para una factura PPD; ejecuta "
                "seed_billing.py y vuelve a intentar."
            )
            return

        origin = next(
            (item for item in candidates if item.member_id), candidates[0]
        )
        admin = session.exec(select(AppUser).order_by(AppUser.email)).first()
        actor_id = admin.id if admin is not None else None

        invoice, _ = billing_service.create_invoice(
            session,
            origin_type=origin.origin_type,
            origin_id=origin.origin_id,
            idempotency_key=f"seed-ppd-invoice-{origin.origin_id}",
            payment_method="PPD",
            payment_form="99",
            actor_id=actor_id,
            **_receptor_for(origin),
        )
        billing_service.stamp_invoice(session, invoice.id, actor_id=actor_id)
        print(
            f"Factura PPD {invoice.folio_label} ({origin.reference}): timbrada en simulación."
        )

        paid_on = club_date(datetime.now(timezone.utc))

        first, _ = billing_service.create_payment_complement(
            session,
            invoice_id=invoice.id,
            amount_cents=max(1, invoice.total_cents * 40 // 100),
            payment_form="03",
            paid_on=paid_on,
            idempotency_key=f"seed-ppd-payment-1-{invoice.id}",
            actor_id=actor_id,
        )
        first = billing_service.stamp_payment_complement(
            session, first.id, actor_id=actor_id
        )
        print(
            f"Complemento {first.folio_label}: parcialidad {first.partiality_number} "
            f"timbrada en simulación; saldo {first.outstanding_balance_cents / 100:.2f}."
        )

        second, _ = billing_service.create_payment_complement(
            session,
            invoice_id=invoice.id,
            amount_cents=max(1, invoice.total_cents * 20 // 100),
            payment_form="04",
            paid_on=paid_on,
            idempotency_key=f"seed-ppd-payment-2-{invoice.id}",
            actor_id=actor_id,
        )
        second = billing_service.stamp_payment_complement(
            session, second.id, actor_id=actor_id
        )
        second = billing_service.cancel_payment_complement(
            session,
            second.id,
            reason_code="03",
            note="Pago registrado por error durante la vista previa",
            actor_id=actor_id,
        )
        print(
            f"Complemento {second.folio_label}: cancelado; el saldo volvió a la factura."
        )

        pending, _ = billing_service.create_payment_complement(
            session,
            invoice_id=invoice.id,
            amount_cents=max(1, invoice.total_cents * 30 // 100),
            payment_form="03",
            paid_on=paid_on,
            idempotency_key=f"seed-ppd-payment-3-{invoice.id}",
            actor_id=actor_id,
        )
        print(
            f"Complemento {pending.folio_label}: solicitud pendiente de timbrado."
        )

        view = billing_service.get_invoice(session, invoice.id)
        print(
            f"Factura {view.folio_label}: total {view.total_cents / 100:.2f} · "
            f"pagado {view.paid_cents / 100:.2f} · "
            f"saldo {view.payment_balance_cents / 100:.2f} · "
            f"estado de pago {view.payment_status}."
        )
        print("Done!")


if __name__ == "__main__":
    main()
