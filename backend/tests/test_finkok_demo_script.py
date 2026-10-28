"""The Finkok demo script builds a sound pre-CFDI and checks the PAC result.

The network half of ``backend/finkok_demo.py`` is manual, but its comprobante
builder and the stamped-XML validator are plain functions and can be tested
here: they decide whether an operator trusts a demo run.
"""

import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from app.modules.billing import cfdi
from app.modules.billing.cfdi import CFDI_NS, IssuerConfig

_SCRIPT = Path(__file__).resolve().parents[1] / "finkok_demo.py"
_spec = importlib.util.spec_from_file_location("finkok_demo", _SCRIPT)
assert _spec is not None and _spec.loader is not None
finkok_demo = importlib.util.module_from_spec(_spec)
# ``dataclasses`` resolves the module through ``sys.modules`` on 3.14.
sys.modules[_spec.name] = finkok_demo
_spec.loader.exec_module(finkok_demo)

ISSUER = IssuerConfig(
    rfc="GARC850312AB1",
    legal_name="Gimnasio Demo",
    tax_regime="612",
    postal_code="06700",
)
RECEPTOR = finkok_demo.Receptor(
    rfc="GARC850312AB1",
    legal_name="Gimnasio Demo",
    tax_regime="612",
    postal_code="06700",
    cfdi_use="G03",
)
UUID = "6C3C0C87-5A34-46F3-BD37-7B79922A51E6"

STAMPED_XML = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
    'Version="4.0" Fecha="2026-10-28T10:15:30" Sello="sello-del-emisor" '
    'NoCertificado="30001000000400002434" SubTotal="100.00" Total="116.00">'
    '<cfdi:Emisor Rfc="GARC850312AB1" Nombre="Gimnasio Demo" RegimenFiscal="612"/>'
    "<cfdi:Complemento>"
    '<tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
    'Version="1.1" UUID="6C3C0C87-5A34-46F3-BD37-7B79922A51E6" '
    'SelloSAT="sello-del-sat" NoCertificadoSAT="30001000000400002495" '
    'FechaTimbrado="2026-10-28T10:15:31" RfcProvCertif="FKR100101XX0"/>'
    "</cfdi:Complemento></cfdi:Comprobante>"
)


def test_demo_comprobante_is_a_valid_prestamp() -> None:
    invoice, items, xml = finkok_demo.build_demo_comprobante(
        issuer=ISSUER,
        receptor=RECEPTOR,
        total_cents=11600,
        tax_rate_percent=16,
        series="DEMO",
        folio=42,
    )

    assert (invoice.subtotal_cents, invoice.tax_cents, invoice.total_cents) == (
        10000,
        1600,
        11600,
    )
    assert items[0].sat_unit_code == "E48"

    root = ET.fromstring(finkok_demo.prepare_prestamp(xml))
    assert root.get("Version") == "4.0"
    assert root.get("Folio") == "42"
    assert root.get("NoCertificado") == ""
    assert root.get("SubTotal") == "100.00"
    assert root.get("Total") == "116.00"
    assert root.find(f"{{{CFDI_NS}}}Emisor").get("Rfc") == "GARC850312AB1"
    concepto = root.find(f"{{{CFDI_NS}}}Conceptos/{{{CFDI_NS}}}Concepto")
    assert concepto.get("Importe") == "100.00"
    assert finkok_demo.prestamp_problems(finkok_demo.prepare_prestamp(xml)) == []


def test_validate_stamped_xml_accepts_a_complete_timbre() -> None:
    problems = finkok_demo.validate_stamped_xml(
        STAMPED_XML,
        expected_uuid=UUID,
        expected_total_cents=11600,
        expected_issuer_rfc="GARC850312AB1",
    )

    assert problems == []


def test_validate_stamped_xml_reports_missing_timbre_and_wrong_uuid() -> None:
    start = STAMPED_XML.index("<cfdi:Complemento>")
    end = STAMPED_XML.index("</cfdi:Complemento>") + len("</cfdi:Complemento>")
    without_timbre = STAMPED_XML[:start] + STAMPED_XML[end:]
    problems = finkok_demo.validate_stamped_xml(without_timbre, expected_uuid=UUID)
    assert any("TimbreFiscalDigital" in problem for problem in problems)

    wrong_uuid = finkok_demo.validate_stamped_xml(
        STAMPED_XML, expected_uuid="00000000-0000-0000-0000-000000000000"
    )
    assert any("UUID" in problem for problem in wrong_uuid)


def test_placeholder_issuer_is_reported_before_stamping() -> None:
    placeholder = IssuerConfig(
        rfc=cfdi.DEFAULT_ISSUER_RFC,
        legal_name=cfdi.DEFAULT_ISSUER_NAME,
        tax_regime=cfdi.DEFAULT_ISSUER_TAX_REGIME,
        postal_code=cfdi.DEFAULT_ISSUER_POSTAL_CODE,
    )
    problems = finkok_demo.issuer_problems(placeholder)

    assert any("GYM_RFC" in problem for problem in problems)
    assert any("GYM_POSTAL_CODE" in problem for problem in problems)
