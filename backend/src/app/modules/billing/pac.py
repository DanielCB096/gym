"""PAC (SAT-authorized stamping provider) boundary.

The club must not pretend to have stamped a comprobante. Only a PAC can seal and
stamp it, so this module exposes a tiny protocol and two implementations:

* ``SimulatedPac`` — used by preview mode and the test suite. It returns the
  same pre-timbre XML with an explicit "SIMULACIÓN" comment, a simulated
  reference and **no** SAT UUID/seal. The invoice is stored with
  ``is_simulated = True``.
* ``FinkokPac`` — the real provider, in ``app.modules.billing.finkok``. It
  needs credentials; without them ``PacUnavailable`` (HTTP 503) is raised
  instead of silently simulating a fiscal document.

Configuration is read per call (like the SMTP transport) so preview and tests can
switch without re-importing the app:

* ``PREVIEW_MODE=true`` or ``PAC_PROVIDER=simulated`` → simulated PAC.
* ``PAC_PROVIDER=finkok`` → Finkok; missing credentials still answer 503.
* any other provider → ``PacUnavailable``.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Protocol
from uuid import uuid4

from app.modules.billing.errors import PacUnavailable


@dataclass(frozen=True)
class StampOutcome:
    provider: str
    provider_reference: str
    stamped_xml: str
    issued_at: datetime
    simulated: bool
    # A real PAC returns the SAT UUID after stamping. Simulation leaves it empty.
    uuid: str | None = None


@dataclass(frozen=True)
class CancellationOutcome:
    provider: str
    accepted: bool
    detail: dict[str, str]
    simulated: bool


@dataclass(frozen=True)
class SatStatusOutcome:
    """What the SAT reports for a stamped comprobante.

    ``estado`` is the life cycle of the CFDI (``Vigente``/``Cancelado``) while
    ``estatus_cancelacion`` is the progress of a cancellation request
    (``En proceso``/``Cancelado``/``No cancelado``). The pair is what tells a
    pending ``202`` apart from a rejection.
    """

    provider: str
    estado: str
    es_cancelable: str
    estatus_cancelacion: str
    codigo_estatus: str
    simulated: bool
    message: str | None = None


class PacGateway(Protocol):
    def stamp(self, xml: str) -> StampOutcome:
        ...

    def cancel(self, *, uuid: str | None, reason_code: str, replacement_uuid: str | None) -> CancellationOutcome:
        ...

    def sat_status(
        self, *, uuid: str, receptor_rfc: str, total_cents: int
    ) -> SatStatusOutcome:
        ...


def _simulated_mode() -> bool:
    provider = os.getenv("PAC_PROVIDER", "").strip().lower()
    preview = os.getenv("PREVIEW_MODE", "").strip().lower() == "true"
    # An unset provider must not fall back to simulation: a real deployment that
    # forgot to configure the PAC has to fail loudly, not issue fake invoices.
    return preview or provider in ("simulated", "preview")


class SimulatedPac:
    """Deterministic, offline stand-in for the PAC.

    It never contacts the network and never fabricates a SAT stamp: the XML is
    returned with a visible simulation marker and no ``TimbreFiscalDigital``.
    """

    provider = "simulated"

    def stamp(self, xml: str) -> StampOutcome:
        reference = f"SIM-{uuid4()}"
        marker = (
            "  <!-- SIMULACION: sin timbre del SAT, sin validez fiscal. "
            "Documento generado en modo vista previa. -->\n"
        )
        stamped_xml = xml.replace("</cfdi:Comprobante>", f"{marker}</cfdi:Comprobante>")
        return StampOutcome(
            provider=self.provider,
            provider_reference=reference,
            stamped_xml=stamped_xml,
            issued_at=datetime.now(timezone.utc),
            simulated=True,
            uuid=None,
        )

    def cancel(
        self,
        *,
        uuid: str | None,
        reason_code: str,
        replacement_uuid: str | None,
    ) -> CancellationOutcome:
        del uuid, replacement_uuid
        return CancellationOutcome(
            provider=self.provider,
            accepted=True,
            detail={"status": "accepted", "reason_code": reason_code, "simulated": "true"},
            simulated=True,
        )

    def sat_status(
        self, *, uuid: str, receptor_rfc: str, total_cents: int
    ) -> SatStatusOutcome:
        del uuid, receptor_rfc, total_cents
        # A simulated cancellation is accepted on the spot, so a simulated
        # status only exists to keep the protocol complete in preview.
        return SatStatusOutcome(
            provider=self.provider,
            estado="Vigente",
            es_cancelable="Cancelable sin aceptación",
            estatus_cancelacion="",
            codigo_estatus="",
            simulated=True,
            message="Estado simulado: no se consultó al SAT.",
        )


def pac_gateway() -> PacGateway:
    """Resolve the configured PAC or raise a clear 503."""

    if _simulated_mode():
        return SimulatedPac()
    provider = os.getenv("PAC_PROVIDER", "").strip().lower()
    if provider == "finkok":
        # Imported here because the adapter imports this module's outcomes.
        from app.modules.billing.finkok import FinkokPac, FinkokSettings

        return FinkokPac(FinkokSettings.from_env())
    configured = provider or "sin configurar"
    raise PacUnavailable(
        f"El PAC '{configured}' no está disponible. Configura PAC_PROVIDER=finkok "
        "con sus credenciales, o PAC_PROVIDER=simulated (o PREVIEW_MODE=true) para "
        "probar el flujo sin validez fiscal."
    )


__all__ = [
    "CancellationOutcome",
    "PacGateway",
    "SatStatusOutcome",
    "SimulatedPac",
    "StampOutcome",
    "pac_gateway",
]
