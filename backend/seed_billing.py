"""Seed the preview database with realistic CFDI invoices.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_billing.py

The script is idempotent: it does nothing when the ``invoices`` table already
has rows. It goes through the billing service so the folios, VAT split, event
trail and simulated stamping behave exactly as in production. Everything is
stamped with the simulated PAC, so the comprobantes carry no SAT UUID and are
clearly marked as fiscally invalid.
"""

import os
import sys

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

DATABASE_URL = "sqlite:///./gym_preview.db"

PUBLIC_GENERAL = {
    "rfc": "XAXX010101000",
    "legal_name": "PÚBLICO EN GENERAL",
    "tax_regime": "616",
    "postal_code": "01000",
    "cfdi_use": "S01",
    "email": None,
}

PERSONAL_RFC = "GARC850312AB1"
SECOND_RFC = "MARE900514CD2"


def _request(session: Session, origin, *, key: str, receptor: dict, actor_id):
    invoice, created = billing_service.create_invoice(
        session,
        origin_type=origin.origin_type,
        origin_id=origin.origin_id,
        idempotency_key=key,
        actor_id=actor_id,
        **receptor,
    )
    if not created:
        print(f"La factura {invoice.folio_label} ya existía.")
    return invoice


def _personal_receptor(origin, rfc: str = PERSONAL_RFC) -> dict:
    if origin.member_id and origin.member_name:
        return {
            "rfc": rfc,
            "legal_name": origin.member_name,
            "tax_regime": "612",
            "postal_code": "06700",
            "cfdi_use": "G03",
            "email": "facturacion@example.com",
        }
    return dict(PUBLIC_GENERAL)


def main() -> None:
    # The script stamps immediately; force the simulated PAC even when it is
    # launched without PREVIEW_MODE set in the shell.
    os.environ.setdefault("PAC_PROVIDER", "simulated")

    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_default_access_control(session)

        if session.exec(select(Invoice)).first() is not None:
            print("Las facturas ya están sembradas; se omite.")
            return

        admin = session.exec(select(AppUser).order_by(AppUser.email)).first()
        actor_id = admin.id if admin is not None else None

        sales = billing_service.list_origin_options(
            session, origin_type="sale", page=1, page_size=10
        )
        payments = billing_service.list_origin_options(
            session, origin_type="membership_payment", page=1, page_size=10
        )
        if len(sales.items) < 2 or len(payments.items) < 2:
            print("Se necesitan al menos dos ventas y dos cobros facturables; se omite.")
            return

        sale_stamped, sale_requested = sales.items[0], sales.items[1]
        payment_stamped, payment_cancelled = payments.items[0], payments.items[1]

        saved_profile = None
        if sale_stamped.member_id and sale_stamped.member_name:
            saved_profile = billing_service.save_fiscal_profile(
                session,
                member_id=sale_stamped.member_id,
                rfc=PERSONAL_RFC,
                legal_name=sale_stamped.member_name,
                tax_regime="612",
                postal_code="06700",
                cfdi_use="G03",
                email="facturacion@example.com",
            )

        # A stamped sale with the member's fiscal profile.
        stamped_sale = _request(
            session,
            sale_stamped,
            key=f"seed-billing-sale-{sale_stamped.origin_id}",
            receptor=_personal_receptor(sale_stamped),
            actor_id=actor_id,
        )
        billing_service.stamp_invoice(session, stamped_sale.id, actor_id=actor_id)
        print(f"Factura {stamped_sale.folio_label} ({sale_stamped.reference}): timbrada en simulación.")

        # A stamped membership payment for the public in general.
        stamped_payment = _request(
            session,
            payment_stamped,
            key=f"seed-billing-payment-{payment_stamped.origin_id}",
            receptor=dict(PUBLIC_GENERAL),
            actor_id=actor_id,
        )
        billing_service.stamp_invoice(session, stamped_payment.id, actor_id=actor_id)
        print(f"Factura {stamped_payment.folio_label} ({payment_stamped.reference}): timbrada en simulación.")

        # One request left pending so the "Timbrar" action can be exercised.
        pending_sale = _request(
            session,
            sale_requested,
            key=f"seed-billing-sale-{sale_requested.origin_id}",
            receptor=dict(PUBLIC_GENERAL),
            actor_id=actor_id,
        )
        print(f"Factura {pending_sale.folio_label} ({sale_requested.reference}): solicitud pendiente de timbrado.")

        # One stamped invoice cancelled, to show the cancellation trail.
        cancelled_payment = _request(
            session,
            payment_cancelled,
            key=f"seed-billing-payment-{payment_cancelled.origin_id}",
            receptor=_personal_receptor(payment_cancelled, rfc=SECOND_RFC),
            actor_id=actor_id,
        )
        billing_service.stamp_invoice(session, cancelled_payment.id, actor_id=actor_id)
        billing_service.cancel_invoice(
            session,
            cancelled_payment.id,
            reason_code="02",
            note="Operación registrada por error durante la vista previa",
            actor_id=actor_id,
        )
        print(f"Factura {cancelled_payment.folio_label} ({payment_cancelled.reference}): cancelada tras timbrar.")

        # Leave at least one member with pending operations and saved fiscal
        # data, so the new-invoice modal demonstrates the profile prefill.
        remaining_sales = billing_service.list_origin_options(
            session, origin_type="sale", page=1, page_size=10
        )
        remaining_payments = billing_service.list_origin_options(
            session, origin_type="membership_payment", page=1, page_size=10
        )
        profile_member = None
        for origin in (*remaining_sales.items, *remaining_payments.items):
            if origin.member_id and origin.member_name and (
                saved_profile is None or origin.member_id != saved_profile.member_id
            ):
                profile_member = billing_service.save_fiscal_profile(
                    session,
                    member_id=origin.member_id,
                    rfc=SECOND_RFC,
                    legal_name=origin.member_name,
                    tax_regime="612",
                    postal_code="06700",
                    cfdi_use="G03",
                    email="facturacion@example.com",
                )
                break
        if profile_member is not None:
            print(f"Perfil fiscal guardado para el socio {profile_member.legal_name}.")

        summary = billing_service.invoice_summary(session)
        print(
            f"Facturas: total {summary.total} · timbradas {summary.stamped} · "
            f"canceladas {summary.cancelled} · por timbrar {summary.requested + summary.failed} · "
            f"simuladas {summary.simulated}"
        )
        print("Done!")


if __name__ == "__main__":
    main()
