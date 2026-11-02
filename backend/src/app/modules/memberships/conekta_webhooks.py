"""Parsing of signed Conekta webhook payloads for hosted membership checkout."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from app.modules.memberships.gateway import ChargeOutcome, ChargeStatus

_SAFE_LOG_CHARACTERS = frozenset("._-")


class ConektaWebhookPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ConektaWebhookEvent:
    provider_event_id: str
    event_type: str
    payload_sha256: str
    provider_order_id: str | None
    amount_cents: int | None
    currency: str | None
    outcome: ChargeOutcome | None


def safe_conekta_webhook_log_context(payload: bytes) -> tuple[str, str]:
    try:
        event = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "unknown", "unknown"
    if not isinstance(event, dict):
        return "unknown", "unknown"
    return (
        _safe_log_value(event.get("id"), 160),
        _safe_log_value(event.get("type"), 100),
    )


def _safe_log_value(value: object, max_length: int) -> str:
    if (
        not isinstance(value, str)
        or not 0 < len(value) <= max_length
        or not value.isascii()
        or any(
            not (character.isalnum() or character in _SAFE_LOG_CHARACTERS)
            for character in value
        )
    ):
        return "unknown"
    return value


def parse_conekta_webhook(payload: bytes) -> ConektaWebhookEvent:
    try:
        event = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConektaWebhookPayloadError("El cuerpo del webhook no es JSON válido.") from error
    if not isinstance(event, dict):
        raise ConektaWebhookPayloadError("El evento de Conekta debe ser un objeto JSON.")

    event_id = event.get("id")
    event_type = event.get("type")
    if not _bounded_string(event_id, 160) or not _bounded_string(event_type, 100):
        raise ConektaWebhookPayloadError("El evento requiere identificador y tipo válidos.")
    if event.get("livemode") is not False:
        raise ConektaWebhookPayloadError("Solo se aceptan eventos de sandbox de Conekta.")

    if event_type == "webhook_ping":
        return ConektaWebhookEvent(
            provider_event_id=event_id,
            event_type=event_type,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            provider_order_id=None,
            amount_cents=None,
            currency=None,
            outcome=None,
        )

    data = event.get("data")
    provider_object = data.get("object") if isinstance(data, dict) else None
    if not isinstance(provider_object, dict):
        raise ConektaWebhookPayloadError("El evento no contiene un objeto de pago válido.")
    if "livemode" in provider_object and provider_object["livemode"] is not False:
        raise ConektaWebhookPayloadError("El objeto de pago no corresponde a sandbox.")

    provider_order_id: str | None = None
    charge_id: str | None = None
    amount: int | None = None
    currency: str | None = None
    outcome: ChargeOutcome | None = None

    if event_type in {"charge.created", "charge.paid", "charge.declined"}:
        if provider_object.get("object") != "charge":
            raise ConektaWebhookPayloadError("El evento de cargo contiene un objeto inesperado.")
        provider_order_id = provider_object.get("order_id")
        charge_id = provider_object.get("id")
        amount = provider_object.get("amount")
        currency = provider_object.get("currency")
        status = provider_object.get("status")
        if (
            not _bounded_string(provider_order_id, 160)
            or not _bounded_string(charge_id, 160)
            or type(amount) is not int
            or amount <= 0
            or not _valid_currency(currency)
        ):
            raise ConektaWebhookPayloadError("El cargo no contiene referencia, importe o moneda válidos.")
        if event_type == "charge.paid":
            if status != "paid":
                raise ConektaWebhookPayloadError("El evento charge.paid no tiene estado paid.")
            outcome = ChargeOutcome(
                status=ChargeStatus.SUCCEEDED,
                provider_reference=charge_id,
                occurred_at=_event_time(event.get("created_at")),
            )
        elif event_type == "charge.declined" or (
            event_type == "charge.created" and status == "declined"
        ):
            if status != "declined":
                raise ConektaWebhookPayloadError("El cargo rechazado no tiene estado declined.")
            outcome = ChargeOutcome(
                status=ChargeStatus.FAILED,
                provider_reference=charge_id,
                failure_code="conekta_declined",
                occurred_at=_event_time(event.get("created_at")),
            )
        elif event_type == "charge.created" and status == "paid":
            outcome = ChargeOutcome(
                status=ChargeStatus.SUCCEEDED,
                provider_reference=charge_id,
                occurred_at=_event_time(event.get("created_at")),
            )
    elif event_type == "order.paid":
        if provider_object.get("object") != "order":
            raise ConektaWebhookPayloadError("El evento order.paid contiene un objeto inesperado.")
        provider_order_id = provider_object.get("id")
        amount = provider_object.get("amount")
        currency = provider_object.get("currency")
        payment_status = provider_object.get("payment_status", provider_object.get("status"))
        charges = provider_object.get("charges")
        charge_data = charges.get("data") if isinstance(charges, dict) else None
        charges_in_order = []
        if isinstance(charge_data, list):
            charges_in_order = [charge for charge in charge_data if isinstance(charge, dict)]
        paid_charge_ids = [
            charge.get("id")
            for charge in charges_in_order
            if charge.get("status") == "paid" and _bounded_string(charge.get("id"), 160)
        ]
        charge_ids = [
            charge.get("id")
            for charge in charges_in_order
            if _bounded_string(charge.get("id"), 160)
        ]
        if (
            not _bounded_string(provider_order_id, 160)
            or type(amount) is not int
            or amount <= 0
            or not _valid_currency(currency)
        ):
            raise ConektaWebhookPayloadError("La orden no contiene referencia, importe o moneda válidos.")
        if payment_status != "paid":
            raise ConektaWebhookPayloadError("El evento order.paid no tiene estado paid.")
        charge_ids = paid_charge_ids or charge_ids
        if len(charge_ids) != 1:
            raise ConektaWebhookPayloadError(
                "La orden pagada debe contener exactamente un cargo identificable."
            )
        charge_id = charge_ids[0]
        outcome = ChargeOutcome(
            status=ChargeStatus.SUCCEEDED,
            provider_reference=charge_id,
            occurred_at=_event_time(event.get("created_at")),
        )

    return ConektaWebhookEvent(
        provider_event_id=event_id,
        event_type=event_type,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        provider_order_id=provider_order_id,
        amount_cents=amount,
        currency=currency,
        outcome=outcome,
    )


def _bounded_string(value: object, max_length: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= max_length


def _valid_currency(value: object) -> bool:
    return isinstance(value, str) and len(value) == 3 and value.isalpha() and value.isupper()


def _event_time(value: object) -> datetime | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ConektaWebhookPayloadError("La fecha del evento no es válida.")
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise ConektaWebhookPayloadError("La fecha del evento no es válida.") from error
