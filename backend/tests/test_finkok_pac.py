"""The Finkok adapter speaks the PAC's SOAP contract without a real network.

``sign_stamp`` seals and stamps in one call, so the adapter only has to clear
the placeholder certificate number and read the UUID and stamped XML back.
Cancellation needs the CSD files; a pending SAT request (202) is never recorded
as cancelled.
"""

from base64 import b64decode
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import httpx
import pytest

from app.modules.billing import finkok
from app.modules.billing.errors import PacRejected, PacUnavailable
from app.modules.billing.finkok import (
    DEMO_BASE_URL,
    FinkokPac,
    FinkokSettings,
    prepare_prestamp,
)
from app.modules.billing.pac import pac_gateway

STAMPED_XML = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
    'Version="4.0" Folio="A-000001" NoCertificado="30001000000400002434">'
    "<cfdi:Complemento><tfd:TimbreFiscalDigital "
    'xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
    'UUID="6C3C0C87-5A34-46F3-BD37-7B79922A51E6"/>'
    "</cfdi:Complemento></cfdi:Comprobante>"
)

PRESTAMP_XML = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
    'Version="4.0" Folio="A-000001" NoCertificado="00000000000000000000" '
    'Total="1160.00"></cfdi:Comprobante>'
)


def _envelope(result: str) -> httpx.Response:
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<senv:Envelope xmlns:senv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:tns="http://facturacion.finkok.com/stamp" '
        'xmlns:can="http://facturacion.finkok.com/cancel" '
        'xmlns:s0="apps.services.soap.core.views" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<senv:Body>{result}</senv:Body></senv:Envelope>"
    )
    return httpx.Response(200, content=body.encode("utf-8"))


def _stamp_success() -> httpx.Response:
    return _envelope(
        "<tns:sign_stampResponse><tns:sign_stampResult>"
        f"<s0:xml><![CDATA[{STAMPED_XML}]]></s0:xml>"
        "<s0:UUID>6C3C0C87-5A34-46F3-BD37-7B79922A51E6</s0:UUID>"
        "<s0:Fecha>2026-10-28T10:15:30</s0:Fecha>"
        "<s0:CodEstatus>Comprobante timbrado satisfactoriamente</s0:CodEstatus>"
        "<s0:Incidencias/>"
        "</tns:sign_stampResult></tns:sign_stampResponse>"
    )


def _stamp_rejection() -> httpx.Response:
    return _envelope(
        "<tns:sign_stampResponse><tns:sign_stampResult>"
        '<s0:xml xsi:nil="true"/><s0:UUID xsi:nil="true"/>'
        "<s0:CodEstatus>El comprobante no cumple con el esquema</s0:CodEstatus>"
        "<s0:Incidencias><s0:Incidencia>"
        "<s0:CodigoError>301</s0:CodigoError>"
        "<s0:MensajeIncidencia>El RFC del receptor no es válido.</s0:MensajeIncidencia>"
        "<s0:ExtraInfo>Receptor.Rfc</s0:ExtraInfo>"
        "</s0:Incidencia></s0:Incidencias>"
        "</tns:sign_stampResult></tns:sign_stampResponse>"
    )


def _cancel_response(
    *,
    status: str = "201",
    estatus: str = "Petición de cancelación realizada exitosamente",
) -> httpx.Response:
    return _envelope(
        "<can:cancelResponse><can:cancelResult><s0:Folios><s0:Folio>"
        "<s0:UUID>6C3C0C87-5A34-46F3-BD37-7B79922A51E6</s0:UUID>"
        f"<s0:EstatusUUID>{status}</s0:EstatusUUID>"
        f"<s0:EstatusCancelacion>{estatus}</s0:EstatusCancelacion>"
        "</s0:Folio></s0:Folios></can:cancelResult></can:cancelResponse>"
    )


def _settings(**overrides: object) -> FinkokSettings:
    values: dict[str, object] = {
        "username": "emisor@example.com",
        "password": "clave-finkok",
        "base_url": DEMO_BASE_URL,
        "taxpayer_id": "EKU9003173C9",
        "cert_path": None,
        "key_path": None,
    }
    values.update(overrides)
    return FinkokSettings(**values)


def _payload(envelope: httpx.Request) -> ET.Element:
    return ET.fromstring(envelope.content)


def _field(envelope: httpx.Request, name: str) -> str | None:
    for node in _payload(envelope).iter():
        if node.tag.rsplit("}", 1)[-1] == name:
            return (node.text or "").strip() or None
    return None


def test_stamp_clears_the_placeholder_certificate_and_keeps_the_sat_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_TIMEZONE", "America/Mexico_City")
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return _stamp_success()

    pac = FinkokPac(_settings(), transport=httpx.MockTransport(handler))
    outcome = pac.stamp(PRESTAMP_XML)

    assert outcome.provider == "finkok"
    assert outcome.uuid == "6C3C0C87-5A34-46F3-BD37-7B79922A51E6"
    assert outcome.provider_reference == outcome.uuid
    assert outcome.simulated is False
    assert "TimbreFiscalDigital" in outcome.stamped_xml
    assert outcome.issued_at == datetime(2026, 10, 28, 16, 15, 30, tzinfo=timezone.utc)

    assert str(sent[0].url) == f"{DEMO_BASE_URL}/servicios/soap/stamp"
    assert sent[0].headers["SOAPAction"] == '"sign_stamp"'
    submitted = b64decode(_field(sent[0], "xml") or "").decode("utf-8")
    assert 'NoCertificado=""' in submitted
    assert "00000000000000000000" not in submitted
    assert _field(sent[0], "username") == "emisor@example.com"
    assert _field(sent[0], "password") == "clave-finkok"


def test_stamp_rejection_carries_the_pac_incidence() -> None:
    pac = FinkokPac(
        _settings(),
        transport=httpx.MockTransport(lambda _: _stamp_rejection()),
    )

    with pytest.raises(PacRejected) as error:
        pac.stamp(PRESTAMP_XML)

    assert "El RFC del receptor no es válido." in str(error.value)
    assert "301" in str(error.value)
    assert error.value.code == "301"


def test_stamp_transport_failure_is_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin ruta al PAC")

    pac = FinkokPac(_settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(PacUnavailable):
        pac.stamp(PRESTAMP_XML)


def test_soap_fault_is_unavailable() -> None:
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soapenv:Body><soapenv:Fault>"
        "<faultcode>soapenv:Server</faultcode>"
        "<faultstring>Credenciales inválidas</faultstring>"
        "</soapenv:Fault></soapenv:Body></soapenv:Envelope>"
    )
    pac = FinkokPac(
        _settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, content=body.encode("utf-8"))
        ),
    )

    with pytest.raises(PacUnavailable) as error:
        pac.stamp(PRESTAMP_XML)

    assert "Credenciales inválidas" in str(error.value)


def test_cancel_sends_the_csd_and_accepts_a_stamped_cancellation(
    tmp_path: Path,
) -> None:
    certificate = b"-----BEGIN CERTIFICATE-----\nMIIBcert\n-----END CERTIFICATE-----\n"
    private_key = b"-----BEGIN PRIVATE KEY-----\nMIIBkey\n-----END PRIVATE KEY-----\n"
    cert_path = tmp_path / "emisor.cer.pem"
    key_path = tmp_path / "emisor.key.pem"
    cert_path.write_bytes(certificate)
    key_path.write_bytes(private_key)
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return _cancel_response()

    pac = FinkokPac(
        _settings(cert_path=str(cert_path), key_path=str(key_path)),
        transport=httpx.MockTransport(handler),
    )
    outcome = pac.cancel(
        uuid="6C3C0C87-5A34-46F3-BD37-7B79922A51E6",
        reason_code="02",
        replacement_uuid=None,
    )

    assert outcome.accepted is True
    assert outcome.simulated is False
    assert outcome.detail["status"] == "201"
    assert str(sent[0].url) == f"{DEMO_BASE_URL}/servicios/soap/cancel"
    assert sent[0].headers["SOAPAction"] == '"cancel"'
    assert _field(sent[0], "taxpayer_id") == "EKU9003173C9"
    assert _field(sent[0], "store_pending") == "0"
    assert b64decode(_field(sent[0], "cer") or "") == certificate
    assert b64decode(_field(sent[0], "key") or "") == private_key
    folio = next(
        node
        for node in _payload(sent[0]).iter()
        if node.tag.rsplit("}", 1)[-1] == "UUID"
    )
    assert folio.attrib == {
        "UUID": "6C3C0C87-5A34-46F3-BD37-7B79922A51E6",
        "FolioSustitucion": "",
        "Motivo": "02",
    }


def test_cancel_pending_at_the_sat_is_not_recorded_as_cancelled(
    tmp_path: Path,
) -> None:
    cert_path = tmp_path / "emisor.cer.pem"
    key_path = tmp_path / "emisor.key.pem"
    cert_path.write_bytes(b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    key_path.write_bytes(b"-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n")
    pac = FinkokPac(
        _settings(cert_path=str(cert_path), key_path=str(key_path)),
        transport=httpx.MockTransport(
            lambda _: _cancel_response(
                status="202", estatus="En proceso de cancelación"
            )
        ),
    )

    outcome = pac.cancel(
        uuid="6C3C0C87-5A34-46F3-BD37-7B79922A51E6",
        reason_code="02",
        replacement_uuid=None,
    )

    assert outcome.accepted is False
    assert outcome.detail["status"] == "202"
    assert "en proceso" in outcome.detail["message"]


def test_cancel_error_without_folios_keeps_the_pac_message(
    tmp_path: Path,
) -> None:
    cert_path = tmp_path / "emisor.cer.pem"
    key_path = tmp_path / "emisor.key.pem"
    cert_path.write_bytes(b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    key_path.write_bytes(b"-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n")
    pac = FinkokPac(
        _settings(cert_path=str(cert_path), key_path=str(key_path)),
        transport=httpx.MockTransport(
            lambda _: _envelope(
                "<can:cancelResponse><can:cancelResult>"
                "<s0:CodEstatus>Motivo cancelación es 01, "
                "FolioSustitucion del CFDI es requerido.</s0:CodEstatus>"
                "</can:cancelResult></can:cancelResponse>"
            )
        ),
    )

    outcome = pac.cancel(
        uuid="6C3C0C87-5A34-46F3-BD37-7B79922A51E6",
        reason_code="02",
        replacement_uuid=None,
    )

    assert outcome.accepted is False
    assert "FolioSustitucion" in outcome.detail["message"]


def test_cancel_requires_the_csd_files(tmp_path: Path) -> None:
    key_path = tmp_path / "emisor.key.pem"
    key_path.write_bytes(b"-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n")
    pac = FinkokPac(
        _settings(key_path=str(key_path)),
        transport=httpx.MockTransport(lambda _: _cancel_response()),
    )

    with pytest.raises(PacUnavailable) as error:
        pac.cancel(
            uuid="6C3C0C87-5A34-46F3-BD37-7B79922A51E6",
            reason_code="02",
            replacement_uuid=None,
        )

    assert "PAC_CERT_PATH" in str(error.value)


def test_gateway_selects_finkok_and_fails_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    monkeypatch.setenv("PAC_PROVIDER", "finkok")
    monkeypatch.setenv("PAC_USER", "emisor@example.com")
    monkeypatch.setenv("PAC_PASSWORD", "clave-finkok")

    gateway = pac_gateway()

    assert isinstance(gateway, FinkokPac)

    monkeypatch.delenv("PAC_USER")
    with pytest.raises(PacUnavailable) as error:
        pac_gateway()
    assert "PAC_USER" in str(error.value)


def test_prepare_prestamp_keeps_an_explicit_certificate() -> None:
    explicit = PRESTAMP_XML.replace("00000000000000000000", "30001000000400002434")

    assert prepare_prestamp(explicit) == explicit
    assert 'NoCertificado=""' in prepare_prestamp(PRESTAMP_XML)
