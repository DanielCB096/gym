"""Prueba de humo del PAC real contra el ambiente demo de Finkok.

Construye un CFDI 4.0 de ejemplo con el mismo constructor que usa facturación,
lo timbra con ``FinkokPac`` y valida el comprobante que devuelve el PAC. No toca
la base de datos ni consume folios del club: la factura vive solo en memoria y
sus archivos quedan en ``finkok_demo_out/`` para revisión.

Uso, desde ``backend`` con el virtualenv:

    .\\.venv\\Scripts\\python.exe finkok_demo.py --dry-run
    .\\.venv\\Scripts\\python.exe finkok_demo.py
    .\\.venv\\Scripts\\python.exe finkok_demo.py --cancel

``--dry-run`` solo arma y muestra el XML pre-timbre; no necesita credenciales.
``--cancel`` exige ``PAC_CERT_PATH`` y ``PAC_KEY_PATH`` con el CSD en PEM y
cancela el comprobante recién timbrado (motivo 02 por defecto).

El script apunta siempre al demo salvo que se pase ``--production
--confirm-production``. Códigos de salida: 0 todo bien, 1 configuración o
validación, 2 rechazo del PAC, 3 PAC inalcanzable (pudo haber timbrado).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

from dotenv import load_dotenv  # noqa: E402

from app.modules.billing import cfdi  # noqa: E402
from app.modules.billing.errors import PacRejected, PacUnavailable  # noqa: E402
from app.modules.billing.finkok import (  # noqa: E402
    DEMO_BASE_URL,
    PRODUCTION_BASE_URL,
    FinkokPac,
    FinkokSettings,
    prepare_prestamp,
)
from app.modules.billing.models import Invoice, InvoiceItem  # noqa: E402
from app.modules.billing.service import issuer_config  # noqa: E402
from app.timezone import club_timezone  # noqa: E402

DEFAULT_OUTPUT_DIR = BASE_DIR / "finkok_demo_out"
DEFAULT_TOTAL_CENTS = 11600
DEFAULT_SERIES = "DEMO"
CANCEL_REASONS = ("01", "02", "03", "04")
UUID_PATTERN = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
PRODUCTION_TRUE = ("true", "1", "yes")


class DemoFailure(Exception):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class Receptor:
    rfc: str
    legal_name: str
    tax_regime: str
    postal_code: str
    cfdi_use: str


def tax_rate_percent() -> int:
    raw = (os.getenv("CFDI_TAX_RATE_PERCENT") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return cfdi.DEFAULT_TAX_RATE_PERCENT
    return value if 0 <= value <= 100 else cfdi.DEFAULT_TAX_RATE_PERCENT


def build_demo_invoice(
    *,
    issuer: cfdi.IssuerConfig,
    receptor: Receptor,
    total_cents: int,
    tax_rate_percent: int,
    series: str,
    folio: int,
) -> tuple[Invoice, list[InvoiceItem]]:
    """Build the unsaved invoice and its single concept for the smoke test."""

    subtotal_cents, tax_cents = cfdi.split_tax_inclusive(total_cents, tax_rate_percent)
    now = datetime.now(timezone.utc)
    invoice = Invoice(
        series=series,
        folio=folio,
        origin_type="sale",
        origin_id=uuid4(),
        origin_reference=f"DEMO-{series}-{folio}"[:64],
        receptor_rfc=receptor.rfc,
        receptor_name=receptor.legal_name,
        receptor_tax_regime=receptor.tax_regime,
        receptor_postal_code=receptor.postal_code,
        receptor_cfdi_use=receptor.cfdi_use,
        currency=cfdi.DEFAULT_CURRENCY,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=total_cents,
        tax_rate_percent=tax_rate_percent,
        payment_form="01",
        payment_method="PUE",
        idempotency_key=f"finkok-demo-{uuid4()}",
        request_fingerprint=sha256(
            f"{series}:{folio}:{now.isoformat()}".encode("utf-8")
        ).hexdigest(),
        issued_at=now,
        created_at=now,
    )
    item = InvoiceItem(
        invoice_id=invoice.id,
        position=1,
        description=(
            f"Servicio de prueba para el timbrado Finkok (serie {series}, folio {folio})"
        )[:300],
        sat_product_code=issuer.service_code,
        sat_unit_code="E48",
        unit_name="Servicio",
        quantity=1,
        unit_price_cents=total_cents,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=total_cents,
    )
    return invoice, [item]


def build_demo_comprobante(
    *,
    issuer: cfdi.IssuerConfig,
    receptor: Receptor,
    total_cents: int,
    tax_rate_percent: int,
    series: str,
    folio: int,
) -> tuple[Invoice, list[InvoiceItem], str]:
    invoice, items = build_demo_invoice(
        issuer=issuer,
        receptor=receptor,
        total_cents=total_cents,
        tax_rate_percent=tax_rate_percent,
        series=series,
        folio=folio,
    )
    xml = cfdi.build_cfdi_xml(invoice=invoice, items=items, issuer=issuer)
    return invoice, items, xml


def issuer_problems(issuer: cfdi.IssuerConfig) -> list[str]:
    """Describe the placeholder or invalid issuer data a real stamp cannot use."""

    problems: list[str] = []
    if issuer.rfc == cfdi.DEFAULT_ISSUER_RFC:
        problems.append(
            "GYM_RFC sigue con el valor de ejemplo (XAXX010101000); usa el RFC "
            "del emisor registrado en Finkok."
        )
    elif not cfdi.RFC_PATTERN.match(issuer.rfc):
        problems.append(f"GYM_RFC no tiene un formato válido: {issuer.rfc!r}.")
    if issuer.legal_name.strip().upper() == cfdi.DEFAULT_ISSUER_NAME.upper():
        problems.append("GYM_LEGAL_NAME sigue con el nombre de ejemplo.")
    if issuer.postal_code == cfdi.DEFAULT_ISSUER_POSTAL_CODE:
        problems.append(
            "GYM_POSTAL_CODE sigue en 00000; usa el domicilio fiscal del emisor."
        )
    elif not cfdi.POSTAL_CODE_PATTERN.match(issuer.postal_code):
        problems.append(f"GYM_POSTAL_CODE no tiene cinco dígitos: {issuer.postal_code!r}.")
    if issuer.tax_regime not in cfdi.TAX_REGIMES:
        problems.append(f"GYM_TAX_REGIME no es una clave del SAT: {issuer.tax_regime!r}.")
    return problems


def prestamp_problems(xml: str) -> list[str]:
    """Checks the XML has the shape a PAC expects before sealing it."""

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        return [f"el XML no se puede parsear: {error}"]
    problems: list[str] = []
    if _local_name(root.tag) != "Comprobante":
        return ["la raíz del XML no es Comprobante"]
    if root.get("Version") != "4.0":
        problems.append("el comprobante no declara Version 4.0")
    for attribute in ("Fecha", "FormaPago", "SubTotal", "Total", "LugarExpedicion"):
        if not (root.get(attribute) or "").strip():
            problems.append(f"el comprobante no trae {attribute}")
    if root.get("NoCertificado") is None:
        problems.append(
            "el comprobante no trae NoCertificado; Finkok no sabría qué CSD usar."
        )
    return problems


def validate_stamped_xml(
    xml: str,
    *,
    expected_uuid: str | None = None,
    expected_total_cents: int | None = None,
    expected_issuer_rfc: str | None = None,
) -> list[str]:
    """Return the problems in the stamped XML; an empty list means it is sound."""

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        return [f"el XML timbrado no se puede parsear: {error}"]
    problems: list[str] = []
    if _local_name(root.tag) != "Comprobante":
        return ["la raíz del XML timbrado no es Comprobante"]
    if root.get("Version") != "4.0":
        problems.append("el comprobante no declara Version 4.0")
    if not (root.get("Fecha") or "").strip():
        problems.append("el comprobante no trae Fecha")
    if not (root.get("Sello") or "").strip():
        problems.append("el comprobante no trae el Sello del emisor")
    if not (root.get("NoCertificado") or "").strip():
        problems.append("el comprobante no trae NoCertificado del emisor")
    if expected_total_cents is not None:
        expected_total = _money(expected_total_cents)
        if (root.get("Total") or "") != expected_total:
            problems.append(
                f"el total del comprobante ({root.get('Total')}) no es {expected_total}"
            )
    if expected_issuer_rfc is not None:
        emisor = _child(root, "Emisor")
        if emisor is None:
            problems.append("el comprobante no trae Emisor")
        elif (emisor.get("Rfc") or "").upper() != expected_issuer_rfc.upper():
            problems.append(
                f"el RFC del emisor ({emisor.get('Rfc')}) no es {expected_issuer_rfc}"
            )

    timbre = _find(root, "TimbreFiscalDigital")
    if timbre is None:
        problems.append("no hay TimbreFiscalDigital: el PAC no timbró el comprobante")
        return problems
    if timbre.get("Version") != "1.1":
        problems.append("el TimbreFiscalDigital no declara Version 1.1")
    uuid = (timbre.get("UUID") or "").strip()
    if not UUID_PATTERN.match(uuid):
        problems.append("el timbre no trae un UUID con formato válido")
    elif expected_uuid and uuid.upper() != expected_uuid.upper():
        problems.append(f"el UUID del timbre ({uuid}) no es el que devolvió el PAC")
    for attribute in ("SelloSAT", "NoCertificadoSAT", "FechaTimbrado", "RfcProvCertif"):
        if not (timbre.get(attribute) or "").strip():
            problems.append(f"el timbre no trae {attribute}")
    return problems


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(element: ET.Element, name: str) -> ET.Element | None:
    for node in element.iter():
        if _local_name(node.tag) == name:
            return node
    return None


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for node in element:
        if _local_name(node.tag) == name:
            return node
    return None


def _money(cents: int) -> str:
    return f"{Decimal(cents) / Decimal(100):.2f}"


def _mask(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[:2]}***"


def _total_cents(raw: str) -> int:
    try:
        value = Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError(f"importe inválido: {raw!r}") from error
    cents = int(value * 100)
    if cents <= 0:
        raise argparse.ArgumentTypeError("el total debe ser mayor que cero")
    return cents


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Timbra un CFDI de prueba contra el ambiente demo de Finkok. "
            "No toca la base de datos ni consume folios del club."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python finkok_demo.py --dry-run\n"
            "  python finkok_demo.py\n"
            "  python finkok_demo.py --cancel --reason 02\n"
            "  python finkok_demo.py --xml factura_pre.xml\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "solo construye el XML pre-timbre con los datos del emisor; no "
            "contacta al PAC ni pide credenciales"
        ),
    )
    parser.add_argument(
        "--xml",
        type=Path,
        help="timbra un XML pre-CFDI existente en vez de armar la factura de ejemplo",
    )
    parser.add_argument(
        "--cancel",
        action="store_true",
        help="cancela el comprobante recién timbrado (exige el CSD en PAC_CERT_PATH/PAC_KEY_PATH)",
    )
    parser.add_argument(
        "--reason",
        choices=CANCEL_REASONS,
        default="02",
        help="motivo de cancelación del SAT (por defecto 02: errores sin relación)",
    )
    parser.add_argument(
        "--replacement-uuid",
        help="UUID que sustituye al comprobante; obligatorio con el motivo 01",
    )
    parser.add_argument("--serie", default=DEFAULT_SERIES, help="serie del comprobante de prueba")
    parser.add_argument("--folio", type=int, help="folio del comprobante de prueba")
    parser.add_argument(
        "--total",
        type=_total_cents,
        default=DEFAULT_TOTAL_CENTS,
        help="total con IVA incluido en pesos (por defecto 116.00)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="carpeta donde guardar la corrida (por defecto finkok_demo_out/)",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="permite timbrar fuera del demo (exige --confirm-production)",
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="confirma que se quiere timbrar en producción aunque esto sea una prueba",
    )
    parser.add_argument("--receptor-rfc", help="RFC del receptor (por defecto, el del emisor)")
    parser.add_argument("--receptor-name", help="razón social del receptor")
    parser.add_argument("--receptor-regime", help="régimen fiscal del receptor")
    parser.add_argument("--receptor-zip", help="código postal fiscal del receptor")
    parser.add_argument("--receptor-use", help="uso del CFDI (por defecto G03)")
    return parser.parse_args(argv)


def _resolve_receptor(args: argparse.Namespace, issuer: cfdi.IssuerConfig) -> Receptor:
    receptor = Receptor(
        rfc=(args.receptor_rfc or issuer.rfc).strip().upper(),
        legal_name=(args.receptor_name or issuer.legal_name).strip(),
        tax_regime=(args.receptor_regime or issuer.tax_regime).strip(),
        postal_code=(args.receptor_zip or issuer.postal_code).strip(),
        cfdi_use=(args.receptor_use or "G03").strip().upper(),
    )
    if not cfdi.RFC_PATTERN.match(receptor.rfc):
        raise DemoFailure(f"El RFC del receptor no es válido: {receptor.rfc!r}.")
    if receptor.rfc == cfdi.PUBLIC_GENERAL_RFC:
        if issuer.rfc == cfdi.DEFAULT_ISSUER_RFC:
            raise DemoFailure(
                "El emisor sigue en el ejemplo y el receptor cae en público en "
                "general, que exige InformacionGlobal. Configura GYM_RFC, "
                "GYM_LEGAL_NAME, GYM_TAX_REGIME y GYM_POSTAL_CODE con los datos "
                "reales, o pasa --receptor-rfc con un RFC real."
            )
        raise DemoFailure(
            "El receptor público en general exige InformacionGlobal (factura global), "
            "que este script no arma. Usa el RFC del emisor o --receptor-rfc con un "
            "RFC real."
        )
    if len(receptor.legal_name) < 2:
        raise DemoFailure("La razón social del receptor es obligatoria.")
    if receptor.tax_regime not in cfdi.TAX_REGIMES:
        raise DemoFailure(f"El régimen del receptor no es una clave del SAT: {receptor.tax_regime!r}.")
    if not cfdi.POSTAL_CODE_PATTERN.match(receptor.postal_code) or receptor.postal_code == "00000":
        raise DemoFailure(
            f"El código postal del receptor no es válido: {receptor.postal_code!r}."
        )
    if receptor.cfdi_use not in cfdi.CFDI_USES:
        raise DemoFailure(f"El uso del CFDI no es una clave válida: {receptor.cfdi_use!r}.")
    return receptor


def _prepare_output_dir(root: Path) -> Path:
    stamp = datetime.now(club_timezone()).strftime("%Y%m%d-%H%M%S")
    folder = root.resolve() / f"{stamp}-{uuid4().hex[:6]}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _save_result(path: Path, data: dict) -> None:
    try:
        _write_json(path, data)
    except OSError as error:
        print(f"Aviso: no se pudo guardar {path}: {error}")


def _configured_target() -> tuple[str, bool]:
    configured = (os.getenv("PAC_BASE_URL") or "").strip().rstrip("/")
    production_env = (os.getenv("PAC_PRODUCTION") or "").strip().lower() in PRODUCTION_TRUE
    target = configured or (PRODUCTION_BASE_URL if production_env else DEMO_BASE_URL)
    return target, production_env


def _guard_target(args: argparse.Namespace) -> tuple[str, bool]:
    """Refuse to leave the demo unless the operator insists twice."""

    configured = (os.getenv("PAC_BASE_URL") or "").strip().rstrip("/")
    production_env = (os.getenv("PAC_PRODUCTION") or "").strip().lower() in PRODUCTION_TRUE
    if args.production:
        if not args.confirm_production:
            raise DemoFailure(
                "--production exige --confirm-production: una prueba no debería "
                "tocar producción por accidente."
            )
        os.environ["PAC_PRODUCTION"] = "true"
        production_env = True
    elif production_env or (configured and configured != DEMO_BASE_URL):
        raise DemoFailure(
            f"El entorno apunta fuera del demo ({configured or PRODUCTION_BASE_URL}). "
            "Este script solo prueba el demo; usa --production --confirm-production "
            "si de verdad quieres timbrar en producción."
        )
    target = configured or (PRODUCTION_BASE_URL if production_env else DEMO_BASE_URL)
    return target, production_env


def _require_cancel_files(args: argparse.Namespace) -> None:
    if args.reason == "01" and not args.replacement_uuid:
        raise DemoFailure(
            "El motivo 01 exige --replacement-uuid con el UUID del comprobante "
            "que sustituye al cancelado."
        )
    for variable in ("PAC_CERT_PATH", "PAC_KEY_PATH"):
        raw = (os.getenv(variable) or "").strip()
        if not raw:
            raise DemoFailure(f"{variable} es obligatorio para cancelar (CSD en PEM).")
        if not Path(raw).is_file():
            raise DemoFailure(f"{variable} no apunta a un archivo existente: {raw}")


def _run(args: argparse.Namespace) -> int:
    load_dotenv()
    print("== Prueba del PAC Finkok ==")

    if args.cancel and args.dry_run:
        raise DemoFailure("--cancel no tiene sentido con --dry-run.")
    if args.production and args.dry_run:
        raise DemoFailure("--production no tiene sentido con --dry-run.")
    if args.dry_run:
        target, production = _configured_target()
        label = "producción" if production else "demo"
        print(f"Destino configurado: {target} ({label}); el dry run no lo usa.")
    else:
        target, production = _guard_target(args)
        print(f"Destino: {target} ({'producción' if production else 'demo'})")
    mode = "producción" if production else "demo"

    if args.cancel:
        _require_cancel_files(args)

    issuer = issuer_config()
    receptor: Receptor | None = None
    invoice: Invoice | None = None
    if args.xml:
        source = args.xml
        if not source.is_file():
            raise DemoFailure(f"No existe el XML de entrada: {source}")
        sent_xml = prepare_prestamp(source.read_text(encoding="utf-8"))
        print(f"Comprobante de entrada: {source}")
    else:
        problems = issuer_problems(issuer)
        if problems:
            if args.dry_run:
                for problem in problems:
                    print(f"Aviso: {problem}")
            else:
                raise DemoFailure(
                    "El emisor no está listo para timbrar:\n"
                    + "\n".join(f"  - {problem}" for problem in problems)
                )
        if issuer.certificate_number != cfdi.DEFAULT_CERTIFICATE_NUMBER:
            print(
                f"Aviso: CFDI_CERTIFICATE_NUMBER está fijado a "
                f"{issuer.certificate_number}; Finkok usará ese CSD y debe coincidir "
                "con el cargado en la cuenta."
            )

        receptor = _resolve_receptor(args, issuer)
        series = (args.serie or "").strip().upper()
        if not series or len(series) > 10:
            raise DemoFailure("La serie debe tener entre 1 y 10 caracteres.")
        folio = (
            args.folio
            if args.folio is not None
            else int(datetime.now(timezone.utc).timestamp())
        )
        if folio <= 0:
            raise DemoFailure("El folio debe ser mayor que cero.")

        rate = tax_rate_percent()
        invoice, _items, xml = build_demo_comprobante(
            issuer=issuer,
            receptor=receptor,
            total_cents=args.total,
            tax_rate_percent=rate,
            series=series,
            folio=folio,
        )
        sent_xml = prepare_prestamp(xml)
        print(
            f"Emisor: {issuer.rfc} · {issuer.legal_name} · régimen "
            f"{issuer.tax_regime} · CP {issuer.postal_code}"
        )
        print(
            f"Receptor: {receptor.rfc} · {receptor.legal_name} · régimen "
            f"{receptor.tax_regime} · CP {receptor.postal_code} · uso {receptor.cfdi_use}"
        )
        if receptor.rfc == issuer.rfc:
            print("Receptor igual al emisor: autofactura de prueba.")
        print(
            f"Comprobante: {series}-{folio} · ${_money(invoice.total_cents)} MXN "
            f"(base ${_money(invoice.subtotal_cents)} + IVA ${_money(invoice.tax_cents)})"
        )

    problems = prestamp_problems(sent_xml)
    if problems:
        raise DemoFailure(
            "El XML pre-timbre no está completo:\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )

    folder = _prepare_output_dir(args.out)
    sent_path = folder / "comprobante_enviado.xml"
    _write_text(sent_path, sent_xml)
    result_path = folder / "resultado.json"
    result: dict = {
        "mode": mode,
        "base_url": target,
        "issuer": (
            None
            if args.xml
            else {
                "rfc": issuer.rfc,
                "legal_name": issuer.legal_name,
                "tax_regime": issuer.tax_regime,
                "postal_code": issuer.postal_code,
            }
        ),
        "receptor": (
            {
                "rfc": receptor.rfc,
                "legal_name": receptor.legal_name,
                "tax_regime": receptor.tax_regime,
                "postal_code": receptor.postal_code,
                "cfdi_use": receptor.cfdi_use,
            }
            if receptor is not None
            else None
        ),
        "comprobante": (
            {"series": invoice.series, "folio": invoice.folio, "total_cents": invoice.total_cents}
            if invoice is not None
            else {"source": str(args.xml)}
        ),
        "sent_xml_sha256": sha256(sent_xml.encode("utf-8")).hexdigest(),
    }

    if args.dry_run:
        result["dry_run"] = True
        _save_result(result_path, result)
        print(f"[1/1] XML pre-timbre guardado en {sent_path}")
        print("Dry run: no se contactó al PAC. Configura las credenciales y repite sin --dry-run.")
        return 0

    provider = (os.getenv("PAC_PROVIDER") or "").strip().lower()
    if provider == "simulated":
        raise DemoFailure(
            "PAC_PROVIDER=simulated: este script prueba el PAC real, no la simulación."
        )
    if provider not in ("", "finkok"):
        raise DemoFailure(
            f"PAC_PROVIDER={provider}: este script solo habla con Finkok; "
            "configura PAC_PROVIDER=finkok."
        )
    if (os.getenv("PREVIEW_MODE") or "").strip().lower() == "true":
        print("Nota: PREVIEW_MODE=true no afecta a este script; siempre usa Finkok.")

    stages = 5 if args.cancel else 4
    print(f"[1/{stages}] XML pre-timbre guardado en {sent_path}")

    try:
        settings = FinkokSettings.from_env()
    except PacUnavailable as error:
        raise DemoFailure(f"Configuración del PAC incompleta: {error}") from error
    if settings.taxpayer_id and settings.taxpayer_id != issuer.rfc:
        print(
            f"Aviso: PAC_TAXPAYER_ID ({settings.taxpayer_id}) no coincide con GYM_RFC "
            f"({issuer.rfc}); la cancelación usará PAC_TAXPAYER_ID."
        )
    print(f"PAC_USER={_mask(settings.username)} · timeout {settings.timeout_seconds:g}s")
    pac = FinkokPac(settings)

    print(f"[2/{stages}] Timbrando ante Finkok...")
    try:
        outcome = pac.stamp(sent_xml)
    except PacRejected as error:
        result["error"] = {"type": "rejected", "message": str(error), "code": error.code}
        _save_result(result_path, result)
        raise DemoFailure(
            f"El PAC rechazó el comprobante: {error}\n"
            f"No se timbró nada. Detalle de la corrida: {result_path}",
            exit_code=2,
        ) from error
    except PacUnavailable as error:
        result["error"] = {"type": "unavailable", "message": str(error)}
        _save_result(result_path, result)
        raise DemoFailure(
            f"No se pudo completar la llamada: {error}\n"
            "El PAC pudo haber timbrado o no. Antes de reintentar, revisa el "
            "portal de Finkok con el RFC emisor; un reintento a ciegas puede "
            f"duplicar el CFDI. Detalle: {result_path}",
            exit_code=3,
        ) from error

    if outcome.uuid is None:
        result["error"] = {"type": "unavailable", "message": "el PAC no devolvió UUID"}
        _save_result(result_path, result)
        raise DemoFailure(
            "El PAC no devolvió un UUID: revisa el portal antes de reintentar.",
            exit_code=3,
        )

    stamped_path = folder / "comprobante_timbrado.xml"
    _write_text(stamped_path, outcome.stamped_xml)
    result["stamped"] = {
        "uuid": outcome.uuid,
        "issued_at": outcome.issued_at.astimezone(timezone.utc).isoformat(),
        "xml_sha256": sha256(outcome.stamped_xml.encode("utf-8")).hexdigest(),
    }
    print(f"      UUID: {outcome.uuid}")
    print(f"      Fecha del PAC: {outcome.issued_at.astimezone(timezone.utc).isoformat()}")

    print(f"[3/{stages}] Validando el XML timbrado...")
    validation = validate_stamped_xml(
        outcome.stamped_xml,
        expected_uuid=outcome.uuid,
        expected_total_cents=invoice.total_cents if invoice is not None else None,
        expected_issuer_rfc=issuer.rfc if invoice is not None else None,
    )
    result["validation"] = {"problems": validation}
    _save_result(result_path, result)
    if validation:
        raise DemoFailure(
            "El PAC respondió, pero el XML timbrado no pasó la validación:\n"
            + "\n".join(f"  - {problem}" for problem in validation)
            + f"\nEl comprobante quedó timbrado con UUID {outcome.uuid}; revisa los "
            f"archivos en {folder} antes de dar la prueba por buena."
        )
    print("      OK: sello, certificado, UUID, emisor, totales y TimbreFiscalDigital.")

    print(f"[4/{stages}] Artefactos guardados en {folder}")

    if not args.cancel:
        _save_result(result_path, result)
        print("Timbrado correcto. Revisa el comprobante en el portal de Finkok (demo).")
        return 0

    print(f"[5/{stages}] Cancelando con motivo {args.reason}...")
    try:
        cancellation = pac.cancel(
            uuid=outcome.uuid,
            reason_code=args.reason,
            replacement_uuid=args.replacement_uuid if args.reason == "01" else None,
        )
    except PacRejected as error:
        result["cancellation"] = {"accepted": False, "error": str(error)}
        _save_result(result_path, result)
        raise DemoFailure(
            f"El comprobante se timbró (UUID {outcome.uuid}), pero el PAC rechazó "
            f"la cancelación: {error}",
            exit_code=2,
        ) from error
    except PacUnavailable as error:
        result["cancellation"] = {"accepted": False, "error": str(error)}
        _save_result(result_path, result)
        raise DemoFailure(
            f"El comprobante se timbró (UUID {outcome.uuid}), pero no se pudo "
            f"contactar al PAC para cancelarlo: {error}\n"
            "Revisa el portal antes de reintentar.",
            exit_code=3,
        ) from error

    result["cancellation"] = {
        "accepted": cancellation.accepted,
        "detail": cancellation.detail,
    }
    _save_result(result_path, result)
    if not cancellation.accepted:
        message = cancellation.detail.get("message") or "sin mensaje del PAC"
        raise DemoFailure(
            f"El comprobante se timbró (UUID {outcome.uuid}), pero la cancelación "
            f"no fue aceptada: {message}",
            exit_code=2,
        )
    print(f"      Cancelación aceptada: {cancellation.detail}")
    print(f"Timbrado y cancelación correctos. Artefactos en {folder}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return _run(args)
    except DemoFailure as failure:
        print(f"\nERROR: {failure}", file=sys.stderr)
        return failure.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
