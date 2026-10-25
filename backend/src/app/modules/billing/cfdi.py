"""CFDI 4.0 helpers: catalogs, validation, VAT split and XML building.

The club's prices are quoted with VAT included (the ticket the member pays is
``total_cents``), so the invoice derives the taxable base from that total:
``base = round(total / (1 + rate))`` and ``tax = total - base``. That keeps the
amount the member paid identical to the CFDI total and makes every line add up.

This module builds the *pre-timbre* comprobante: the XML a PAC receives before
it seals and stamps it. The certificate number, the seal and the
``TimbreFiscalDigital`` come from the PAC, so they are not invented here. In
simulation the PAC returns the same XML with an explicit "SIMULACIÓN" comment
and the invoice is flagged as simulated: it is never a valid fiscal document.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Sequence
from xml.etree import ElementTree as ET

from app.modules.billing.errors import FiscalDataInvalid
from app.modules.billing.models import Invoice, InvoiceItem, InvoicePayment
from app.timezone import to_club_timezone

CFDI_NS = "http://www.sat.gob.mx/cfd/4"
PAGO20_NS = "http://www.sat.gob.mx/Pagos20"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
DEFAULT_CURRENCY = "MXN"
DEFAULT_TAX_RATE_PERCENT = 16

# Receptor of a factura global. The SAT requires this exact name, the generic
# RFC and the "sin obligaciones fiscales" regime; the fiscal postal code is the
# issuer's. ``InformacionGlobal`` with a monthly period is mandatory for it.
PUBLIC_GENERAL_RFC = "XAXX010101000"
PUBLIC_GENERAL_NAME = "PUBLICO EN GENERAL"
PUBLIC_GENERAL_TAX_REGIME = "616"
PUBLIC_GENERAL_CFDI_USE = "S01"
GLOBAL_PERIODICITY_MONTHLY = "03"
# SAT relationship used by a credit note (CFDI de egreso) to point at the
# comprobante it adjusts: 01 = "Nota de crédito de los documentos relacionados".
CREDIT_NOTE_RELATION_CODE = "01"
# A payment complement (CFDI tipo P) points at the PPD invoice it pays with
# TipoRelacion 07 = "CFDI por aplicación de anticipo o pago en parcialidades".
PAYMENT_COMPLEMENT_RELATION_CODE = "07"
PAYMENT_COMPLEMENT_USO_CFDI = "CP01"
PAYMENT_COMPLEMENT_PRODUCT_CODE = "84111506"
PAYMENT_COMPLEMENT_UNIT_CODE = "ACT"
PAYMENT_COMPLEMENT_DESCRIPTION = "Pago"

# SAT catalogs. Only the codes the club actually uses are listed; an unknown
# code is rejected instead of being sent to the PAC and failing there.
TAX_REGIMES = frozenset(
    {
        "601", "603", "605", "606", "607", "608", "609", "610", "611", "612",
        "614", "615", "616", "620", "621", "622", "623", "624", "625", "626",
        "628", "629", "630",
    }
)
CFDI_USES = frozenset(
    {
        "G01", "G02", "G03",
        "D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10",
        "I01", "I02", "I03", "I04", "I05", "I06", "I07", "I08",
        "P01", "S01", "CP01", "CN01",
    }
)
PAYMENT_FORMS = frozenset(
    {"01", "02", "03", "04", "05", "06", "08", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "99"}
)
PAYMENT_FORM_BY_METHOD = {
    "cash": "01",
    "transfer": "03",
    "card": "04",
    "account": "99",
}
RFC_PATTERN = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
POSTAL_CODE_PATTERN = re.compile(r"^\d{5}$")

# Placeholders for the issuer. They are valid shapes so preview and tests can
# issue a simulated comprobante out of the box; a real stamp must configure the
# club's own data through the environment.
DEFAULT_ISSUER_RFC = "XAXX010101000"
DEFAULT_ISSUER_NAME = "CENTRO FIT"
DEFAULT_ISSUER_TAX_REGIME = "601"
DEFAULT_ISSUER_POSTAL_CODE = "00000"
DEFAULT_CERTIFICATE_NUMBER = "00000000000000000000"
DEFAULT_PRODUCT_CODE = "01010101"
DEFAULT_SERVICE_CODE = "90121500"


@dataclass(frozen=True)
class FiscalData:
    rfc: str
    legal_name: str
    tax_regime: str
    postal_code: str
    cfdi_use: str
    email: str | None = None


@dataclass(frozen=True)
class IssuerConfig:
    rfc: str
    legal_name: str
    tax_regime: str
    postal_code: str
    certificate_number: str = DEFAULT_CERTIFICATE_NUMBER
    product_code: str = DEFAULT_PRODUCT_CODE
    service_code: str = DEFAULT_SERVICE_CODE


def normalize_fiscal_data(
    *,
    rfc: str,
    legal_name: str,
    tax_regime: str,
    postal_code: str,
    cfdi_use: str,
    email: str | None = None,
) -> FiscalData:
    """Trim and validate the receptor data against the CFDI 4.0 catalogs."""

    normalized_rfc = (rfc or "").strip().upper()
    if not RFC_PATTERN.match(normalized_rfc):
        raise FiscalDataInvalid(
            "El RFC no tiene un formato válido (12 o 13 caracteres).", field="rfc"
        )

    normalized_name = " ".join((legal_name or "").split())
    if len(normalized_name) < 2:
        raise FiscalDataInvalid("La razón social es obligatoria.", field="legal_name")
    if len(normalized_name) > 254:
        raise FiscalDataInvalid("La razón social excede 254 caracteres.", field="legal_name")

    normalized_regime = (tax_regime or "").strip()
    if normalized_regime not in TAX_REGIMES:
        raise FiscalDataInvalid(
            "El régimen fiscal no es una clave del SAT válida.", field="tax_regime"
        )

    normalized_zip = (postal_code or "").strip()
    if not POSTAL_CODE_PATTERN.match(normalized_zip):
        raise FiscalDataInvalid(
            "El código postal fiscal debe tener 5 dígitos.", field="postal_code"
        )
    if normalized_zip == "00000":
        raise FiscalDataInvalid(
            "El código postal fiscal no puede ser 00000.", field="postal_code"
        )

    normalized_use = (cfdi_use or "").strip().upper()
    if normalized_use not in CFDI_USES:
        raise FiscalDataInvalid("El uso de CFDI no es una clave válida.", field="cfdi_use")

    normalized_email = (email or "").strip().lower() or None
    if normalized_email is not None and (
        "@" not in normalized_email or len(normalized_email) > 254
    ):
        raise FiscalDataInvalid("El correo del receptor no es válido.", field="email")

    return FiscalData(
        rfc=normalized_rfc,
        legal_name=normalized_name,
        tax_regime=normalized_regime,
        postal_code=normalized_zip,
        cfdi_use=normalized_use,
        email=normalized_email,
    )


def split_tax_inclusive(total_cents: int, tax_rate_percent: int) -> tuple[int, int]:
    """Split a VAT-included amount into ``(subtotal, tax)`` in cents.

    ``total_cents`` is what the member paid. Rounding is half-up so a 1-cent
    difference never leaves a negative base and the two parts always add back
    to the original total.
    """

    if total_cents < 0:
        raise ValueError("total_cents must be non-negative")
    if tax_rate_percent < 0:
        raise ValueError("tax_rate_percent must be non-negative")
    if total_cents == 0 or tax_rate_percent == 0:
        return total_cents, 0
    with localcontext() as context:
        context.prec = 18
        subtotal = (
            Decimal(total_cents) * 100 / (100 + tax_rate_percent)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    base = int(subtotal)
    return base, total_cents - base


def payment_form_for_method(method: str) -> str:
    return PAYMENT_FORM_BY_METHOD.get(method, "99")


def _money(cents: int) -> str:
    value = (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:.2f}"


def _unit_price(cents: int, quantity: int) -> str:
    # CFDI allows up to six decimals in ValorUnitario; Importe stays at two.
    value = (Decimal(cents) / Decimal(100) / Decimal(quantity)).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    return f"{value:.6f}"


def _tax_rate_fraction(tax_rate_percent: int) -> str:
    value = (Decimal(tax_rate_percent) / Decimal(100)).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    return f"{value:.6f}"


def _cfdi_datetime(moment: datetime) -> str:
    return to_club_timezone(moment).strftime("%Y-%m-%dT%H:%M:%S")


def build_cfdi_xml(
    *,
    invoice: Invoice,
    items: Sequence[InvoiceItem],
    issuer: IssuerConfig,
    simulated: bool = False,
    related_uuid: str | None = None,
) -> str:
    """Build the CFDI 4.0 comprobante (pre-timbre) for a stamped/simulated invoice."""

    ET.register_namespace("cfdi", CFDI_NS)
    ET.register_namespace("xsi", XSI_NS)
    is_credit_note = invoice.origin_type == "credit_note"
    root = ET.Element(
        f"{{{CFDI_NS}}}Comprobante",
        {
            "Version": "4.0",
            "Serie": invoice.series,
            "Folio": str(invoice.folio),
            "Fecha": _cfdi_datetime(invoice.issued_at or invoice.created_at),
            "FormaPago": invoice.payment_form,
            "NoCertificado": issuer.certificate_number,
            "SubTotal": _money(invoice.subtotal_cents),
            "Moneda": invoice.currency or DEFAULT_CURRENCY,
            "Total": _money(invoice.total_cents),
            "TipoDeComprobante": "E" if is_credit_note else "I",
            "Exportacion": "01",
            "MetodoPago": invoice.payment_method,
            "LugarExpedicion": issuer.postal_code,
            f"{{{XSI_NS}}}schemaLocation": (
                f"{CFDI_NS} http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd"
            ),
        },
    )

    if invoice.origin_type == "global":
        if invoice.global_year is None or invoice.global_month is None:
            raise ValueError("A global invoice requires its club-local period")
        ET.SubElement(
            root,
            f"{{{CFDI_NS}}}InformacionGlobal",
            {
                "Periodicidad": GLOBAL_PERIODICITY_MONTHLY,
                "Meses": f"{invoice.global_month:02d}",
                "Año": str(invoice.global_year),
            },
        )

    if is_credit_note:
        if related_uuid:
            related = ET.SubElement(
                root,
                f"{{{CFDI_NS}}}CfdiRelacionados",
                {"TipoRelacion": CREDIT_NOTE_RELATION_CODE},
            )
            ET.SubElement(
                related,
                f"{{{CFDI_NS}}}CfdiRelacionado",
                {"UUID": related_uuid},
            )
        else:
            # A simulated original has no SAT UUID, so the relation cannot be
            # written as a real CfdiRelacionado. The internal link is stored in
            # the invoice and the document stays flagged as a simulation.
            root.append(
                ET.Comment(
                    " SIMULACION: la factura relacionada no tiene UUID del SAT; "
                    "el vinculo se conserva en el sistema. "
                )
            )

    ET.SubElement(
        root,
        f"{{{CFDI_NS}}}Emisor",
        {
            "Rfc": issuer.rfc,
            "Nombre": issuer.legal_name,
            "RegimenFiscal": issuer.tax_regime,
        },
    )
    ET.SubElement(
        root,
        f"{{{CFDI_NS}}}Receptor",
        {
            "Rfc": invoice.receptor_rfc,
            "Nombre": invoice.receptor_name,
            "DomicilioFiscalReceptor": invoice.receptor_postal_code,
            "RegimenFiscalReceptor": invoice.receptor_tax_regime,
            "UsoCFDI": invoice.receptor_cfdi_use,
        },
    )

    concepts = ET.SubElement(root, f"{{{CFDI_NS}}}Conceptos")
    for item in items:
        concept = ET.SubElement(
            concepts,
            f"{{{CFDI_NS}}}Concepto",
            {
                "ClaveProdServ": item.sat_product_code,
                "Cantidad": str(item.quantity),
                "ClaveUnidad": item.sat_unit_code,
                "Unidad": item.unit_name,
                "Descripcion": item.description,
                "ValorUnitario": _unit_price(item.subtotal_cents, item.quantity),
                "Importe": _money(item.subtotal_cents),
                "ObjetoImp": "02",
            },
        )
        if item.tax_cents > 0:
            taxes = ET.SubElement(concept, f"{{{CFDI_NS}}}Impuestos")
            transfers = ET.SubElement(taxes, f"{{{CFDI_NS}}}Traslados")
            ET.SubElement(
                transfers,
                f"{{{CFDI_NS}}}Traslado",
                {
                    "Base": _money(item.subtotal_cents),
                    "Impuesto": "002",
                    "TipoFactor": "Tasa",
                    "TasaOCuota": _tax_rate_fraction(invoice.tax_rate_percent),
                    "Importe": _money(item.tax_cents),
                },
            )

    if invoice.tax_cents > 0:
        total_taxes = ET.SubElement(
            root,
            f"{{{CFDI_NS}}}Impuestos",
            {"TotalImpuestosTrasladados": _money(invoice.tax_cents)},
        )
        transfers = ET.SubElement(total_taxes, f"{{{CFDI_NS}}}Traslados")
        ET.SubElement(
            transfers,
            f"{{{CFDI_NS}}}Traslado",
            {
                "Base": _money(invoice.subtotal_cents),
                "Impuesto": "002",
                "TipoFactor": "Tasa",
                "TasaOCuota": _tax_rate_fraction(invoice.tax_rate_percent),
                "Importe": _money(invoice.tax_cents),
            },
        )

    if simulated:
        root.append(
            ET.Comment(
                " SIMULACION: comprobante sin timbre del SAT, sin validez fiscal. "
                "Generado en modo vista previa. "
            )
        )

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode", xml_declaration=False
    )


def _pago20_totals(payment: InvoicePayment, base_cents: int, tax_cents: int) -> dict[str, str]:
    totals = {"MontoTotalPagos": _money(payment.amount_cents)}
    if tax_cents <= 0:
        return totals
    suffix = "8" if payment.tax_rate_percent == 8 else "16"
    totals[f"TotalTrasladosBaseIVA{suffix}"] = _money(base_cents)
    totals[f"TotalTrasladosImpuestoIVA{suffix}"] = _money(tax_cents)
    return totals


def build_payment_complement_xml(
    *,
    payment: InvoicePayment,
    invoice: Invoice,
    issuer: IssuerConfig,
    related_uuid: str | None = None,
    simulated: bool = False,
) -> str:
    """Build the CFDI 4.0 payment complement (tipo P, Pagos 2.0).

    The complement pays one partiality of a PPD invoice: it has no concepts of
    its own (the fixed "Pago" concept has zero value), carries the related
    invoice UUID and splits the paid amount into VAT base and tax. Without a
    UUID for the original (simulated stamping) the relation cannot be written,
    so the XML keeps an explicit simulation comment instead of inventing one.
    """

    ET.register_namespace("cfdi", CFDI_NS)
    ET.register_namespace("pago20", PAGO20_NS)
    ET.register_namespace("xsi", XSI_NS)
    base_cents, tax_cents = split_tax_inclusive(
        payment.amount_cents, payment.tax_rate_percent
    )
    root = ET.Element(
        f"{{{CFDI_NS}}}Comprobante",
        {
            "Version": "4.0",
            "Serie": payment.series,
            "Folio": str(payment.folio),
            "Fecha": _cfdi_datetime(payment.issued_at or payment.created_at),
            "NoCertificado": issuer.certificate_number,
            "SubTotal": "0.00",
            "Moneda": "XXX",
            "Total": "0.00",
            "TipoDeComprobante": "P",
            "Exportacion": "01",
            "LugarExpedicion": issuer.postal_code,
            f"{{{XSI_NS}}}schemaLocation": (
                f"{CFDI_NS} http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd "
                f"{PAGO20_NS} http://www.sat.gob.mx/sitio_internet/cfd/Pagos/Pagos20.xsd"
            ),
        },
    )

    if related_uuid:
        related = ET.SubElement(
            root,
            f"{{{CFDI_NS}}}CfdiRelacionados",
            {"TipoRelacion": PAYMENT_COMPLEMENT_RELATION_CODE},
        )
        ET.SubElement(
            related,
            f"{{{CFDI_NS}}}CfdiRelacionado",
            {"UUID": related_uuid},
        )
    else:
        root.append(
            ET.Comment(
                " SIMULACION: la factura pagada no tiene UUID del SAT; "
                "el vinculo se conserva en el sistema. "
            )
        )

    ET.SubElement(
        root,
        f"{{{CFDI_NS}}}Emisor",
        {
            "Rfc": issuer.rfc,
            "Nombre": issuer.legal_name,
            "RegimenFiscal": issuer.tax_regime,
        },
    )
    ET.SubElement(
        root,
        f"{{{CFDI_NS}}}Receptor",
        {
            "Rfc": invoice.receptor_rfc,
            "Nombre": invoice.receptor_name,
            "DomicilioFiscalReceptor": invoice.receptor_postal_code,
            "RegimenFiscalReceptor": invoice.receptor_tax_regime,
            "UsoCFDI": PAYMENT_COMPLEMENT_USO_CFDI,
        },
    )

    concepts = ET.SubElement(root, f"{{{CFDI_NS}}}Conceptos")
    ET.SubElement(
        concepts,
        f"{{{CFDI_NS}}}Concepto",
        {
            "ClaveProdServ": PAYMENT_COMPLEMENT_PRODUCT_CODE,
            "Cantidad": "1",
            "ClaveUnidad": PAYMENT_COMPLEMENT_UNIT_CODE,
            "Descripcion": PAYMENT_COMPLEMENT_DESCRIPTION,
            "ValorUnitario": "0.00",
            "Importe": "0.00",
            "ObjetoImp": "01",
        },
    )

    complement = ET.SubElement(root, f"{{{CFDI_NS}}}Complemento")
    pagos = ET.SubElement(
        complement,
        f"{{{PAGO20_NS}}}Pagos",
        {"Version": "2.0"},
    )
    ET.SubElement(
        pagos,
        f"{{{PAGO20_NS}}}Totales",
        _pago20_totals(payment, base_cents, tax_cents),
    )
    pago = ET.SubElement(
        pagos,
        f"{{{PAGO20_NS}}}Pago",
        {
            "FechaPago": f"{payment.paid_on.isoformat()}T12:00:00",
            "FormaDePagoP": payment.payment_form,
            "MonedaP": payment.currency,
            "TipoCambioP": "1",
            "Monto": _money(payment.amount_cents),
        },
    )
    document_attributes = {
        "Serie": invoice.series,
        "Folio": str(invoice.folio),
        "MonedaDR": invoice.currency,
        "EquivalenciaDR": "1",
        "NumParcialidad": str(payment.partiality_number),
        "ImpSaldoAnt": _money(payment.prior_balance_cents),
        "ImpPagado": _money(payment.amount_cents),
        "ImpSaldoInsoluto": _money(payment.outstanding_balance_cents),
        "ObjetoImpDR": "02" if tax_cents > 0 else "01",
    }
    if related_uuid:
        document_attributes = {"IdDocumento": related_uuid, **document_attributes}
    document = ET.SubElement(
        pago,
        f"{{{PAGO20_NS}}}DoctoRelacionado",
        document_attributes,
    )
    if not related_uuid:
        document.append(
            ET.Comment(
                " SIMULACION: IdDocumento se omite porque la factura original "
                "no tiene UUID del SAT. "
            )
        )
    if tax_cents > 0:
        taxes_dr = ET.SubElement(document, f"{{{PAGO20_NS}}}ImpuestosDR")
        transfers_dr = ET.SubElement(taxes_dr, f"{{{PAGO20_NS}}}TrasladosDR")
        ET.SubElement(
            transfers_dr,
            f"{{{PAGO20_NS}}}TrasladoDR",
            {
                "BaseDR": _money(base_cents),
                "ImpuestoDR": "002",
                "TipoFactorDR": "Tasa",
                "TasaOCuotaDR": _tax_rate_fraction(payment.tax_rate_percent),
                "ImporteDR": _money(tax_cents),
            },
        )
        taxes_p = ET.SubElement(pago, f"{{{PAGO20_NS}}}ImpuestosP")
        transfers_p = ET.SubElement(taxes_p, f"{{{PAGO20_NS}}}TrasladosP")
        ET.SubElement(
            transfers_p,
            f"{{{PAGO20_NS}}}TrasladoP",
            {
                "BaseP": _money(base_cents),
                "ImpuestoP": "002",
                "TipoFactorP": "Tasa",
                "TasaOCuotaP": _tax_rate_fraction(payment.tax_rate_percent),
                "ImporteP": _money(tax_cents),
            },
        )

    if simulated:
        root.append(
            ET.Comment(
                " SIMULACION: complemento de pago sin timbre del SAT, sin validez "
                "fiscal. Generado en modo vista previa. "
            )
        )

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode", xml_declaration=False
    )


def invoice_xml_filename(invoice: Invoice) -> str:
    suffix = "-simulada" if invoice.is_simulated else ""
    return f"CFDI-{invoice.series}-{invoice.folio:06d}{suffix}.xml"


def payment_complement_xml_filename(payment: InvoicePayment) -> str:
    suffix = "-simulada" if payment.is_simulated else ""
    return f"PAGO-{payment.series}-{payment.folio:06d}{suffix}.xml"


__all__ = [
    "CFDI_NS",
    "CFDI_USES",
    "CREDIT_NOTE_RELATION_CODE",
    "DEFAULT_CERTIFICATE_NUMBER",
    "DEFAULT_ISSUER_NAME",
    "DEFAULT_ISSUER_POSTAL_CODE",
    "DEFAULT_ISSUER_RFC",
    "DEFAULT_ISSUER_TAX_REGIME",
    "DEFAULT_PRODUCT_CODE",
    "DEFAULT_SERVICE_CODE",
    "FiscalData",
    "GLOBAL_PERIODICITY_MONTHLY",
    "IssuerConfig",
    "PAGO20_NS",
    "PAYMENT_COMPLEMENT_DESCRIPTION",
    "PAYMENT_COMPLEMENT_PRODUCT_CODE",
    "PAYMENT_COMPLEMENT_RELATION_CODE",
    "PAYMENT_COMPLEMENT_UNIT_CODE",
    "PAYMENT_COMPLEMENT_USO_CFDI",
    "PAYMENT_FORMS",
    "PUBLIC_GENERAL_CFDI_USE",
    "PUBLIC_GENERAL_NAME",
    "PUBLIC_GENERAL_RFC",
    "PUBLIC_GENERAL_TAX_REGIME",
    "TAX_REGIMES",
    "build_cfdi_xml",
    "build_payment_complement_xml",
    "invoice_xml_filename",
    "normalize_fiscal_data",
    "payment_complement_xml_filename",
    "payment_form_for_method",
    "split_tax_inclusive",
]
