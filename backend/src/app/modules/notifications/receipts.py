"""Signed provider acknowledgements for the staff emails.

The delivery row records what the club's SMTP server answered; it cannot know
what happened to the message afterwards. A mail provider reports that later —
the mailbox accepted it, the address bounced, the recipient marked it as spam —
through a webhook, and this module turns the report into an append-only receipt
attached to the delivery. The transport status is never rewritten: ``sent``
still means "the server accepted the message", and the receipt says whether it
arrived.

The endpoint has no account to authenticate with, so the body is signed with a
shared secret (``EMAIL_WEBHOOK_SECRET``) and the signature travels in
``X-Email-Signature`` as ``sha256=<hex>``. Providers retry until they get a 2xx,
so the provider's event id makes the write idempotent: the same event stored
twice would otherwise look like two acknowledgements. When the club connects a
real provider, an adapter translates its payload into this contract.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.notifications.models import (
    MAX_MESSAGE_ID_CHARS,
    MAX_PROVIDER_EVENT_CHARS,
    RECEIPT_EVENT_TYPES,
    StaffNotificationDelivery,
    StaffNotificationDeliveryReceipt,
    utc_now,
)

WEBHOOK_SECRET_ENV = "EMAIL_WEBHOOK_SECRET"
SIGNATURE_PREFIX = "sha256="
MAX_DETAIL_CHARS = 500
# Only a message that actually left can be acknowledged: a pending row has no
# provider event yet and a simulated one never contacted a server.
ACKNOWLEDGEABLE_DELIVERY_STATUSES = ("sent",)


class ReceiptError(Exception):
    pass


class ReceiptNotConfigured(ReceiptError):
    pass


class ReceiptSignatureInvalid(ReceiptError):
    pass


class ReceiptInvalid(ReceiptError):
    """The body does not respect the webhook contract."""


class ReceiptNotFound(ReceiptError):
    pass


class ReceiptRejected(ReceiptError):
    """The report is well formed but conflicts with the delivery's state."""


@dataclass(frozen=True)
class EmailDeliveryReport:
    message_id: str
    provider_event_id: str
    event_type: str
    occurred_at: datetime | None
    detail: str | None


def webhook_secret() -> str:
    return os.getenv(WEBHOOK_SECRET_ENV, "").strip()


def signature_for(raw_body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_signature(
    raw_body: bytes, signature: str | None, *, secret: str | None = None
) -> None:
    configured = webhook_secret() if secret is None else secret.strip()
    if not configured:
        raise ReceiptNotConfigured(
            f"El webhook de acuse no está configurado ({WEBHOOK_SECRET_ENV})."
        )
    candidate = (signature or "").strip()
    if not candidate:
        raise ReceiptSignatureInvalid("Falta la firma del webhook.")
    if not hmac.compare_digest(signature_for(raw_body, configured), candidate):
        raise ReceiptSignatureInvalid("La firma del webhook no coincide.")


def normalize_message_id(value: str) -> str:
    """The stored id is bare (``token@domain``); providers may echo ``<...>``."""

    return value.strip().strip("<>").strip().lower()


def parse_delivery_report(raw_body: bytes) -> EmailDeliveryReport:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReceiptInvalid("El cuerpo del webhook no es JSON válido.") from error
    if not isinstance(payload, dict):
        raise ReceiptInvalid("El cuerpo del webhook debe ser un objeto JSON.")

    message_id = normalize_message_id(_text(payload.get("message_id")))
    if not message_id or len(message_id) > MAX_MESSAGE_ID_CHARS:
        raise ReceiptInvalid("El webhook no trae un identificador de mensaje válido.")

    provider_event_id = _text(payload.get("event_id"))
    if not provider_event_id or len(provider_event_id) > MAX_PROVIDER_EVENT_CHARS:
        raise ReceiptInvalid("El webhook no trae un identificador de evento válido.")

    event_type = _text(payload.get("event"))
    if event_type not in RECEIPT_EVENT_TYPES:
        raise ReceiptInvalid(
            "El evento debe ser 'delivered', 'bounced' o 'complained'."
        )

    return EmailDeliveryReport(
        message_id=message_id,
        provider_event_id=provider_event_id,
        event_type=event_type,
        occurred_at=_parse_moment(payload.get("occurred_at")),
        detail=_optional_text(payload.get("detail")),
    )


def record_email_receipt(
    session: Session,
    report: EmailDeliveryReport,
    *,
    now: datetime | None = None,
) -> tuple[StaffNotificationDeliveryReceipt, bool]:
    """Store one acknowledgement, or return the one already stored.

    The boolean says whether the row is new, so the webhook can answer a replay
    with the same 2xx without pretending to have stored it twice.
    """

    occurred = _as_utc(now or utc_now())
    delivery = session.exec(
        select(StaffNotificationDelivery).where(
            StaffNotificationDelivery.message_id == report.message_id
        )
    ).first()
    if delivery is None:
        raise ReceiptNotFound("No se encontró el correo del acuse.")
    if delivery.status not in ACKNOWLEDGEABLE_DELIVERY_STATUSES:
        raise ReceiptRejected(
            "El correo todavía no se ha enviado; no hay entrega que acusar."
        )

    existing = _by_event_id(session, report.provider_event_id)
    if existing is not None:
        return _replayed(existing, delivery.id)

    receipt = StaffNotificationDeliveryReceipt(
        delivery_id=delivery.id,
        provider_event_id=report.provider_event_id,
        event_type=report.event_type,
        occurred_at=_as_utc(report.occurred_at or occurred),
        detail=report.detail,
        received_at=occurred,
    )
    session.add(receipt)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        # Two identical deliveries of the same webhook raced; the unique event
        # id lets one row win and the loser answers as a replay.
        session.expunge(receipt)
        winner = _by_event_id(session, report.provider_event_id)
        if winner is None:
            raise
        return _replayed(winner, delivery.id)
    session.commit()
    session.refresh(receipt)
    return receipt, True


def _by_event_id(
    session: Session, provider_event_id: str
) -> StaffNotificationDeliveryReceipt | None:
    return session.exec(
        select(StaffNotificationDeliveryReceipt).where(
            StaffNotificationDeliveryReceipt.provider_event_id == provider_event_id
        )
    ).first()


def _replayed(
    receipt: StaffNotificationDeliveryReceipt, delivery_id: UUID
) -> tuple[StaffNotificationDeliveryReceipt, bool]:
    if receipt.delivery_id != delivery_id:
        raise ReceiptRejected(
            "El identificador del evento ya se usó para otro correo."
        )
    return receipt, False


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    clean = _text(value)
    return clean[:MAX_DETAIL_CHARS] or None


def _parse_moment(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ReceiptInvalid("La fecha del acuse no es válida.")
    raw = value.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReceiptInvalid("La fecha del acuse no es válida.") from error


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


__all__ = [
    "ACKNOWLEDGEABLE_DELIVERY_STATUSES",
    "EmailDeliveryReport",
    "ReceiptError",
    "ReceiptInvalid",
    "ReceiptNotConfigured",
    "ReceiptNotFound",
    "ReceiptRejected",
    "ReceiptSignatureInvalid",
    "WEBHOOK_SECRET_ENV",
    "normalize_message_id",
    "parse_delivery_report",
    "record_email_receipt",
    "signature_for",
    "verify_signature",
    "webhook_secret",
]
