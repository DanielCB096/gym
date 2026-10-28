"""Finkok PAC adapter (SAT-authorized stamping provider).

``sign_stamp`` makes Finkok seal the pre-CFDI with the CSD registered in the
emitter's Finkok profile and then stamp it, so stamping never handles the
private key here. Cancellation is the exception: Finkok's ``cancel`` requires
the emitter's CSD as PEM (the key already encrypted in 3DES with the passphrase
Finkok provides) plus the ``taxpayer_id``, so ``PAC_CERT_PATH`` and
``PAC_KEY_PATH`` must point at files the operator prepared offline.

Only ``201`` (cancelled) and ``205`` (already cancelled) count as accepted.
``202`` means the SAT kept the request pending; this domain has no pending
state, so the invoice stays ``stamped`` with the PAC's message and the operator
checks the SAT/Finkok portal before retrying.
"""

from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import httpx

from app.modules.billing.errors import PacRejected, PacUnavailable
from app.modules.billing.pac import CancellationOutcome, StampOutcome
from app.timezone import club_timezone

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
STAMP_NS = "http://facturacion.finkok.com/stamp"
CANCEL_NS = "http://facturacion.finkok.com/cancel"
VIEWS_NS = "apps.services.soap.core.views"

DEMO_BASE_URL = "https://demo-facturacion.finkok.com"
PRODUCTION_BASE_URL = "https://facturacion.finkok.com"
SUCCESS_STATUS = "Comprobante timbrado satisfactoriamente"
ACCEPTED_CANCEL_STATUSES = ("201", "205")
DEFAULT_TIMEOUT_SECONDS = 30.0

ET.register_namespace("soapenv", SOAP_NS)
ET.register_namespace("stam", STAMP_NS)
ET.register_namespace("can", CANCEL_NS)
ET.register_namespace("apps", VIEWS_NS)

_PLACEHOLDER_CERTIFICATE = re.compile(r'NoCertificado="(?:0{20})?"')


@dataclass(frozen=True)
class FinkokSettings:
    username: str
    password: str
    base_url: str
    taxpayer_id: str
    cert_path: str | None
    key_path: str | None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "FinkokSettings":
        username = (os.getenv("PAC_USER") or "").strip()
        password = (os.getenv("PAC_PASSWORD") or "").strip()
        if not username or not password:
            raise PacUnavailable(
                "PAC_PROVIDER=finkok requiere PAC_USER y PAC_PASSWORD; sin "
                "credenciales no se puede timbrar."
            )
        base_url = (os.getenv("PAC_BASE_URL") or "").strip()
        if not base_url:
            production = (os.getenv("PAC_PRODUCTION") or "").strip().lower()
            base_url = (
                PRODUCTION_BASE_URL
                if production in ("true", "1", "yes")
                else DEMO_BASE_URL
            )
        return cls(
            username=username,
            password=password,
            base_url=base_url.rstrip("/"),
            taxpayer_id=(
                os.getenv("PAC_TAXPAYER_ID") or os.getenv("GYM_RFC") or ""
            ).strip().upper(),
            cert_path=(os.getenv("PAC_CERT_PATH") or "").strip() or None,
            key_path=(os.getenv("PAC_KEY_PATH") or "").strip() or None,
            timeout_seconds=_timeout_seconds(os.getenv("PAC_TIMEOUT_SECONDS")),
        )


def _timeout_seconds(raw: str | None) -> float:
    try:
        value = float((raw or "").strip())
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


def prepare_prestamp(xml: str) -> str:
    """Clear the placeholder certificate number before ``sign_stamp``.

    Finkok seals with the last CSD registered for the RFC unless the XML names
    a specific ``NoCertificado``. The builder's twenty-zero placeholder is not
    a real certificate, so it must not select anything.
    """

    return _PLACEHOLDER_CERTIFICATE.sub('NoCertificado=""', xml, count=1)


def _stamp_envelope(settings: FinkokSettings, xml: str) -> bytes:
    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    ET.SubElement(envelope, f"{{{SOAP_NS}}}Header")
    body = ET.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    operation = ET.SubElement(body, f"{{{STAMP_NS}}}sign_stamp")
    ET.SubElement(operation, f"{{{STAMP_NS}}}xml").text = b64encode(
        xml.encode("utf-8")
    ).decode("ascii")
    ET.SubElement(operation, f"{{{STAMP_NS}}}username").text = settings.username
    ET.SubElement(operation, f"{{{STAMP_NS}}}password").text = settings.password
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def _cancel_envelope(
    settings: FinkokSettings,
    *,
    uuid: str,
    reason_code: str,
    replacement_uuid: str | None,
    certificate: str,
    private_key: str,
) -> bytes:
    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    ET.SubElement(envelope, f"{{{SOAP_NS}}}Header")
    body = ET.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    operation = ET.SubElement(body, f"{{{CANCEL_NS}}}cancel")
    uuids = ET.SubElement(operation, f"{{{CANCEL_NS}}}UUIDS")
    ET.SubElement(
        uuids,
        f"{{{VIEWS_NS}}}UUID",
        {
            "UUID": uuid,
            "FolioSustitucion": replacement_uuid or "",
            "Motivo": reason_code,
        },
    )
    ET.SubElement(operation, f"{{{CANCEL_NS}}}username").text = settings.username
    ET.SubElement(operation, f"{{{CANCEL_NS}}}password").text = settings.password
    ET.SubElement(operation, f"{{{CANCEL_NS}}}taxpayer_id").text = settings.taxpayer_id
    ET.SubElement(operation, f"{{{CANCEL_NS}}}cer").text = certificate
    ET.SubElement(operation, f"{{{CANCEL_NS}}}key").text = private_key
    ET.SubElement(operation, f"{{{CANCEL_NS}}}store_pending").text = "0"
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(element: ET.Element, name: str) -> ET.Element | None:
    for node in element.iter():
        if _local_name(node.tag) == name:
            return node
    return None


def _text(element: ET.Element, name: str) -> str | None:
    node = _first(element, name)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _incidences(result: ET.Element) -> list[dict[str, str | None]]:
    found = []
    for node in result.iter():
        if _local_name(node.tag) != "Incidencia":
            continue
        found.append(
            {
                "code": _text(node, "CodigoError"),
                "message": _text(node, "MensajeIncidencia"),
                "extra": _text(node, "ExtraInfo"),
            }
        )
    return found


def _cancel_folios(result: ET.Element) -> list[dict[str, str | None]]:
    folios = []
    for node in result.iter():
        if _local_name(node.tag) != "Folio":
            continue
        folios.append(
            {
                "uuid": _text(node, "UUID"),
                "status": _text(node, "EstatusUUID"),
                "estatus": _text(node, "EstatusCancelacion"),
            }
        )
    return folios


def _rejection_message(
    incidences: list[dict[str, str | None]], status: str | None
) -> str:
    if incidences:
        first = incidences[0]
        message = first["message"] or "El PAC rechazó el comprobante."
        return f"{message} (código {first['code']})" if first["code"] else message
    return status or "El PAC rechazó el comprobante sin indicar el motivo."


def _cancel_rejection_message(folio: dict[str, str | None]) -> str:
    status = folio["status"] or ""
    estatus = folio["estatus"]
    if status == "202":
        return (
            "El SAT dejó la cancelación en proceso; el comprobante sigue vigente. "
            "Consulta el estatus en el portal de Finkok antes de reintentar."
        )
    if status == "203":
        return "El SAT no encontró el comprobante con ese UUID."
    if status == "204":
        message = "El SAT no permite cancelar este comprobante (código 204)."
        return f"{message} {estatus}" if estatus else message
    if estatus:
        return f"El PAC rechazó la cancelación: {estatus}"
    return f"El PAC rechazó la cancelación (código {status or 'desconocido'})."


def _parse_issued_at(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=club_timezone())
    return parsed.astimezone(timezone.utc)


def _read_pem(path: str | None, variable: str) -> str:
    if not path:
        raise PacUnavailable(
            f"La cancelación ante Finkok requiere {variable} con el CSD en PEM."
        )
    file = Path(path)
    try:
        content = file.read_bytes()
    except OSError as error:
        raise PacUnavailable(f"No se pudo leer {variable}: {file.name}.") from error
    if b"-----BEGIN" not in content:
        raise PacUnavailable(f"{variable} debe apuntar a un archivo PEM.")
    return b64encode(content).decode("ascii")


class FinkokPac:
    provider = "finkok"

    def __init__(
        self,
        settings: FinkokSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def stamp(self, xml: str) -> StampOutcome:
        envelope = _stamp_envelope(self._settings, prepare_prestamp(xml))
        result = self._post("/servicios/soap/stamp", "sign_stamp", envelope)
        status = _text(result, "CodEstatus")
        uuid = _text(result, "UUID")
        stamped_xml = _text(result, "xml")
        incidences = _incidences(result)
        if status != SUCCESS_STATUS and not (uuid and stamped_xml and not incidences):
            raise PacRejected(
                _rejection_message(incidences, status),
                code=incidences[0]["code"] if incidences else None,
            )
        if not uuid or not stamped_xml:
            raise PacUnavailable(
                "El PAC informó el timbrado pero no devolvió el comprobante; "
                "revisa el portal de Finkok antes de reintentar."
            )
        return StampOutcome(
            provider=self.provider,
            provider_reference=uuid,
            stamped_xml=stamped_xml,
            issued_at=_parse_issued_at(_text(result, "Fecha")),
            simulated=False,
            uuid=uuid,
        )

    def cancel(
        self,
        *,
        uuid: str | None,
        reason_code: str,
        replacement_uuid: str | None,
    ) -> CancellationOutcome:
        if not uuid:
            raise PacRejected(
                "El comprobante no tiene UUID del SAT; no se puede cancelar ante el PAC."
            )
        if not self._settings.taxpayer_id:
            raise PacUnavailable(
                "La cancelación ante Finkok requiere PAC_TAXPAYER_ID o GYM_RFC."
            )
        envelope = _cancel_envelope(
            self._settings,
            uuid=uuid,
            reason_code=reason_code,
            replacement_uuid=replacement_uuid,
            certificate=_read_pem(self._settings.cert_path, "PAC_CERT_PATH"),
            private_key=_read_pem(self._settings.key_path, "PAC_KEY_PATH"),
        )
        result = self._post("/servicios/soap/cancel", "cancel", envelope)
        cod_status = _text(result, "CodEstatus")
        folios = _cancel_folios(result)
        if not folios:
            return CancellationOutcome(
                provider=self.provider,
                accepted=False,
                detail={
                    "status": "",
                    "message": cod_status
                    or "El PAC no devolvió el resultado de la cancelación.",
                },
                simulated=False,
            )
        folio = folios[0]
        accepted = folio["status"] in ACCEPTED_CANCEL_STATUSES
        detail = {
            "uuid": folio["uuid"] or uuid,
            "status": folio["status"] or "",
            "estatus_cancelacion": folio["estatus"] or "",
        }
        if cod_status:
            detail["cod_estatus"] = cod_status
        if not accepted:
            detail["message"] = _cancel_rejection_message(folio)
        return CancellationOutcome(
            provider=self.provider,
            accepted=accepted,
            detail=detail,
            simulated=False,
        )

    def _post(self, path: str, action: str, envelope: bytes) -> ET.Element:
        url = f"{self._settings.base_url}{path}"
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{action}"',
        }
        try:
            with httpx.Client(
                timeout=self._settings.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(url, content=envelope, headers=headers)
        except httpx.HTTPError as error:
            raise PacUnavailable(
                f"No se pudo contactar al PAC ({error.__class__.__name__}); "
                "el comprobante no se envió al SAT."
            ) from error

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as error:
            if response.status_code >= 400:
                raise PacUnavailable(
                    f"El PAC respondió HTTP {response.status_code} sin un "
                    "cuerpo SOAP legible."
                ) from error
            raise PacUnavailable(
                "El PAC respondió con un cuerpo que no es XML."
            ) from error

        body = root.find(f"{{{SOAP_NS}}}Body")
        if body is None:
            raise PacUnavailable("El PAC respondió sin un sobre SOAP.")
        fault = body.find(f"{{{SOAP_NS}}}Fault")
        if fault is not None:
            message = _text(fault, "faultstring") or _text(fault, "Text")
            raise PacUnavailable(
                f"El PAC rechazó la petición SOAP: {message}"
                if message
                else "El PAC rechazó la petición SOAP."
            )
        if response.status_code >= 400:
            raise PacUnavailable(f"El PAC respondió HTTP {response.status_code}.")
        if len(body) == 0:
            raise PacUnavailable("El PAC respondió sin resultado.")
        return body[0]


__all__ = [
    "FinkokPac",
    "FinkokSettings",
    "prepare_prestamp",
]
