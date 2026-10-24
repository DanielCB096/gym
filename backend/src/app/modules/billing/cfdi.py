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
from app.modules.billing.models import Invoice, InvoiceItem
from app.timezone import to_club_timezone

CFDI_NS = "http://www.sat.gob.mx/cfd/4"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
DEFAULT_CURRENCY = "MXN"
DEFAULT_TAX_RATE_PERCENT = 16

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
) -> str:
    """Build the CFDI 4.0 comprobante (pre-timbre) for a stamped/simulated invoice."""

    ET.register_namespace("cfdi", CFDI_NS)
    ET.register_namespace("xsi", XSI_NS)
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
            "TipoDeComprobante": "I",
            "Exportacion": "01",
            "MetodoPago": invoice.payment_method,
            "LugarExpedicion": issuer.postal_code,
            f"{{{XSI_NS}}}schemaLocation": (
                f"{CFDI_NS} http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd"
            ),
        },
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


def invoice_xml_filename(invoice: Invoice) -> str:
    suffix = "-simulada" if invoice.is_simulated else ""
    return f"CFDI-{invoice.series}-{invoice.folio:06d}{suffix}.xml"


__all__ = [
    "CFDI_NS",
    "CFDI_USES",
    "DEFAULT_CERTIFICATE_NUMBER",
    "DEFAULT_ISSUER_NAME",
    "DEFAULT_ISSUER_POSTAL_CODE",
    "DEFAULT_ISSUER_RFC",
    "DEFAULT_ISSUER_TAX_REGIME",
    "DEFAULT_PRODUCT_CODE",
    "DEFAULT_SERVICE_CODE",
    "FiscalData",
    "IssuerConfig",
    "PAYMENT_FORMS",
    "TAX_REGIMES",
    "build_cfdi_xml",
    "invoice_xml_filename",
    "normalize_fiscal_data",
    "payment_form_for_method",
    "split_tax_inclusive",
]
