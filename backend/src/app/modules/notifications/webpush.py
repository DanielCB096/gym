"""Web Push for the panel's staff accounts.

The member app reaches phones through Expo; the staff works in the browser, so
this channel speaks the Web Push protocol instead. The browser registers a
subscription with its push service, the panel stores it with the account that
opted in, and each new staff notice queues one delivery per active
subscription —written in the same transaction as the notice—. A short pass
after the response encrypts the message with the club's VAPID key and the
device's public key, and records the outcome.

There is no worker here either: the pass rides the same background hook as the
staff email queue, and the panel can send or retry by hand. Preview mode
simulates the delivery, so a demo never rings a real browser. A failed push is
never retried automatically: a broken push channel would otherwise alert the
accounts that operate the panel, whose alerts would fail too.

Rows are claimed with a compare-and-set on ``attempts`` before the request
leaves, which keeps two concurrent passes from pushing the same notice twice.
"""

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from urllib.parse import urlparse
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import func, update
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.mailer import preview_mode
from app.modules.identity.models import AppUser, Employee
from app.modules.notifications.models import (
    MAX_PUSH_ENDPOINT_CHARS,
    MAX_PUSH_KEY_CHARS,
    StaffNotification,
    StaffPushDelivery,
    StaffPushSubscription,
    utc_now,
)

logger = logging.getLogger(__name__)

VAPID_PRIVATE_KEY_ENV = "VAPID_PRIVATE_KEY"
VAPID_SUBJECT_ENV = "VAPID_SUBJECT"
DEFAULT_VAPID_SUBJECT = "mailto:avisos@centro-fit.local"
DEFAULT_SEND_BATCH_LIMIT = 20
MAX_SEND_BATCH_LIMIT = 100
DEFAULT_DELIVERY_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 10.0
# The push service keeps an undelivered message this long before dropping it;
# a notice about today's work is not useful hours later.
PUSH_TTL_SECONDS = 3600
DELIVERY_STATUSES = ("pending", "sent", "simulated", "failed")
RETRYABLE_DELIVERY_STATUSES = ("failed",)
# An uncompressed P-256 point (0x04 + 32 + 32) and the 16-byte auth secret.
P256DH_BYTES = 65
AUTH_BYTES = 16
GONE_STATUS_CODES = (404, 410)


class StaffPushError(Exception):
    pass


class InvalidPushSubscription(StaffPushError):
    pass


class StaffPushSubscriptionNotFound(StaffPushError):
    pass


class StaffPushDeliveryNotFound(StaffPushError):
    pass


class StaffPushDeliveryRetryNotAllowed(StaffPushError):
    pass


class WebPushDeliveryFailed(Exception):
    pass


class WebPushSubscriptionGone(WebPushDeliveryFailed):
    """The push service said the browser no longer exists (404/410)."""


@dataclass(frozen=True)
class VapidConfig:
    private_key: bytes
    public_key: str
    subject: str


@dataclass(frozen=True)
class StaffPushConfig:
    enabled: bool
    public_key: str | None = None
    subject: str | None = None


@dataclass(frozen=True)
class StaffPushSendResult:
    status: str


@dataclass(frozen=True)
class StaffPushPass:
    attempted: int
    sent: int
    simulated: int
    failed: int
    deactivated: int
    remaining: int


@dataclass(frozen=True)
class StaffPushSubscriptionItem:
    id: UUID
    device: str
    user_agent: str | None
    active: bool
    created_at: datetime
    last_seen_at: datetime | None
    deactivated_at: datetime | None


@dataclass(frozen=True)
class StaffPushDeliveryItem:
    id: UUID
    notice_id: UUID
    user_id: UUID
    user_name: str
    user_email: str
    kind: str
    title: str
    device: str
    status: str
    attempts: int
    error: str | None
    created_at: datetime
    last_attempt_at: datetime | None
    sent_at: datetime | None


@dataclass(frozen=True)
class StaffPushDeliveryPage:
    items: list[StaffPushDeliveryItem]
    total: int
    page: int
    page_size: int
    pages: int


@dataclass(frozen=True)
class StaffPushDeliveryCounts:
    pending: int
    sent: int
    simulated: int
    failed: int
    active_subscriptions: int


def _encode_base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    text = (value or "").strip()
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + padding)
    except (ValueError, binascii.Error) as error:
        raise ValueError("no es base64url válido") from error


def vapid_config() -> VapidConfig | None:
    """The club's signing key, or ``None`` when the channel is not configured.

    Only the private key is stored: the public key the browser needs is derived
    from it, so an operator cannot publish one key and sign with another by
    mistake.
    """

    raw = os.getenv(VAPID_PRIVATE_KEY_ENV, "").strip()
    if not raw:
        return None
    subject = (
        os.getenv(VAPID_SUBJECT_ENV, "").strip() or DEFAULT_VAPID_SUBJECT
    )
    if not (subject.startswith("mailto:") or subject.startswith("https://")):
        raise ValueError(
            f"{VAPID_SUBJECT_ENV} debe ser una dirección mailto: o una URL https."
        )
    try:
        private_raw = _decode_base64url(raw)
    except ValueError as error:
        raise ValueError(f"{VAPID_PRIVATE_KEY_ENV} no es base64url válido.") from error
    if len(private_raw) != 32:
        raise ValueError(f"{VAPID_PRIVATE_KEY_ENV} debe tener 32 bytes.")
    private_key = ec.derive_private_key(
        int.from_bytes(private_raw, "big"), ec.SECP256R1()
    )
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return VapidConfig(
        private_key=private_raw,
        public_key=_encode_base64url(public_raw),
        subject=subject,
    )


def read_staff_push_config() -> StaffPushConfig:
    """What the panel needs to subscribe: whether keys exist and the public one.

    A malformed configuration is treated as absent and logged: the panel shows
    the channel as not configured instead of failing every request.
    """

    try:
        config = vapid_config()
    except ValueError as error:
        logger.warning("VAPID del push del personal inválido: %s", error)
        return StaffPushConfig(enabled=False)
    if config is None:
        return StaffPushConfig(enabled=False)
    return StaffPushConfig(
        enabled=True, public_key=config.public_key, subject=config.subject
    )


def clean_push_endpoint(raw: str) -> str:
    """A browser subscription always points to https; localhost is the dev case."""

    endpoint = (raw or "").strip()
    parsed = urlparse(endpoint)
    if len(endpoint) > MAX_PUSH_ENDPOINT_CHARS:
        raise InvalidPushSubscription(
            "La suscripción del navegador es demasiado larga."
        )
    secure = parsed.scheme == "https" and bool(parsed.hostname)
    local = (
        parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
    )
    if not (secure or local):
        raise InvalidPushSubscription(
            "La suscripción del navegador no tiene una dirección válida."
        )
    return endpoint


def _clean_key(raw: str, *, name: str, size: int) -> str:
    text = (raw or "").strip()
    if len(text) > MAX_PUSH_KEY_CHARS:
        raise InvalidPushSubscription(
            f"La clave {name} de la suscripción es demasiado larga."
        )
    try:
        decoded = _decode_base64url(text)
    except ValueError as error:
        raise InvalidPushSubscription(
            f"La clave {name} de la suscripción no es válida."
        ) from error
    if len(decoded) != size:
        raise InvalidPushSubscription(
            f"La clave {name} de la suscripción no es válida."
        )
    return text


def mask_push_endpoint(endpoint: str) -> str:
    """Keep the push service host and the tail; the path is a capability URL."""

    host = urlparse(endpoint).hostname or "push"
    return f"{host}/…{endpoint[-6:]}" if len(endpoint) > 6 else host


def register_staff_push_subscription(
    session: Session,
    user_id: UUID,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> StaffPushSubscription:
    """Attach a browser to the account, transferring it if it belonged to another.

    The same browser profile can sign in with another account later; the
    subscription follows the account that registered it last instead of leaving
    the previous one receiving the new one's notices.
    """

    clean_endpoint = clean_push_endpoint(endpoint)
    clean_p256dh = _clean_key(p256dh, name="p256dh", size=P256DH_BYTES)
    clean_auth = _clean_key(auth, name="auth", size=AUTH_BYTES)
    user = session.get(AppUser, user_id)
    if user is None or user.status != "active":
        raise InvalidPushSubscription("La cuenta no está activa.")
    occurred = _as_utc(now or utc_now())
    agent = (user_agent or "").strip()[:255] or None
    row = session.exec(
        select(StaffPushSubscription).where(
            StaffPushSubscription.endpoint == clean_endpoint
        )
    ).first()
    if row is None:
        row = StaffPushSubscription(
            user_id=user_id,
            endpoint=clean_endpoint,
            p256dh=clean_p256dh,
            auth=clean_auth,
            user_agent=agent,
            created_at=occurred,
            last_seen_at=occurred,
        )
    else:
        row.user_id = user_id
        row.p256dh = clean_p256dh
        row.auth = clean_auth
        row.user_agent = agent
        row.active = True
        row.deactivated_at = None
        row.last_seen_at = occurred
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def deactivate_staff_push_subscription(
    session: Session,
    user_id: UUID,
    subscription_id: UUID,
    *,
    now: datetime | None = None,
) -> StaffPushSubscription:
    """Silence one browser the account registered; only its owner can do it."""

    row = session.get(StaffPushSubscription, subscription_id)
    if row is None or row.user_id != user_id:
        raise StaffPushSubscriptionNotFound(
            "No se encontró la suscripción del navegador."
        )
    if row.active:
        row.active = False
        row.deactivated_at = _as_utc(now or utc_now())
        session.add(row)
        session.commit()
    session.refresh(row)
    return row


def list_staff_push_subscriptions(
    session: Session, user_id: UUID
) -> list[StaffPushSubscriptionItem]:
    rows = session.exec(
        select(StaffPushSubscription)
        .where(StaffPushSubscription.user_id == user_id)
        .order_by(StaffPushSubscription.created_at.desc())
    ).all()
    return [staff_push_subscription_item(row) for row in rows]


def send_staff_web_push(
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    title: str,
    body: str,
    data: dict[str, str],
) -> StaffPushSendResult:
    """Encrypt and deliver one message; ``simulated`` in preview mode."""

    if preview_mode():
        return StaffPushSendResult(status="simulated")
    try:
        config = vapid_config()
    except ValueError as error:
        raise WebPushDeliveryFailed(
            "La configuración VAPID del club no es válida."
        ) from error
    if config is None:
        raise WebPushDeliveryFailed(
            "El push del personal no está configurado: faltan las claves VAPID."
        )
    payload = json.dumps(
        {"title": title, "body": body, "data": data}, ensure_ascii=False
    )
    try:
        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=payload,
            vapid_private_key=Vapid.from_raw(config.private_key),
            vapid_claims={"sub": config.subject},
            content_encoding="aes128gcm",
            ttl=PUSH_TTL_SECONDS,
            timeout=_timeout_seconds(),
        )
    except WebPushException as error:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        if status_code in GONE_STATUS_CODES:
            raise WebPushSubscriptionGone(
                "El navegador ya no recibe notificaciones; se retiró la suscripción."
            ) from error
        detail = (
            f"El servicio de notificaciones respondió {status_code}."
            if status_code
            else (str(error).strip() or "El servicio de notificaciones rechazó el mensaje.")
        )
        raise WebPushDeliveryFailed(detail[:500]) from error
    except Exception as error:  # noqa: BLE001 - one bad push must not stop the pass
        raise WebPushDeliveryFailed(
            (str(error).strip() or error.__class__.__name__)[:500]
        ) from error
    return StaffPushSendResult(status="sent")


def _timeout_seconds() -> float:
    try:
        return float(
            os.getenv("STAFF_PUSH_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
        )
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def staff_push_subscription_item(
    row: StaffPushSubscription,
) -> StaffPushSubscriptionItem:
    return StaffPushSubscriptionItem(
        id=row.id,
        device=mask_push_endpoint(row.endpoint),
        user_agent=row.user_agent,
        active=row.active,
        created_at=_as_utc(row.created_at),
        last_seen_at=(
            _as_utc(row.last_seen_at) if row.last_seen_at is not None else None
        ),
        deactivated_at=(
            _as_utc(row.deactivated_at)
            if row.deactivated_at is not None
            else None
        ),
    )


def _remaining_count(session: Session) -> int:
    return int(
        session.exec(
            select(func.count(StaffPushDelivery.id)).where(
                StaffPushDelivery.status == "pending"
            )
        ).one()
        or 0
    )


def _claim(
    session: Session,
    delivery: StaffPushDelivery,
    *,
    from_status: str,
    now: datetime,
) -> bool:
    """Count the attempt and commit it before the request leaves."""

    result = session.exec(
        update(StaffPushDelivery)
        .where(
            StaffPushDelivery.id == delivery.id,
            StaffPushDelivery.status == from_status,
            StaffPushDelivery.attempts == delivery.attempts,
        )
        .values(
            attempts=StaffPushDelivery.attempts + 1,
            last_attempt_at=now,
        )
    )
    session.commit()
    if not result.rowcount:
        session.refresh(delivery)
        return False
    session.refresh(delivery)
    return True


def _deliver(
    session: Session, delivery: StaffPushDelivery, *, now: datetime
) -> bool:
    """Send one claimed push; return whether the subscription was retired."""

    notice = session.get(StaffNotification, delivery.notice_id)
    subscription = session.get(StaffPushSubscription, delivery.subscription_id)
    if notice is None or subscription is None:
        # The foreign keys make these unreachable; a row must not stay pending
        # forever if they ever happen.
        delivery.status = "failed"
        delivery.error = (
            "El aviso o la suscripción del navegador ya no existen."
        )
        session.add(delivery)
        session.commit()
        return False
    if not subscription.active:
        delivery.status = "failed"
        delivery.error = "La suscripción del navegador ya no está activa."
        session.add(delivery)
        session.commit()
        return False
    data = {"notification_id": str(notice.id), "kind": notice.kind}
    if notice.ref_id is not None:
        data["ref_id"] = str(notice.ref_id)
    try:
        result = send_staff_web_push(
            endpoint=delivery.endpoint,
            p256dh=subscription.p256dh,
            auth=subscription.auth,
            title=notice.title,
            body=notice.body,
            data=data,
        )
    except WebPushSubscriptionGone as error:
        delivery.status = "failed"
        delivery.error = str(error)[:500]
        session.add(delivery)
        session.exec(
            update(StaffPushSubscription)
            .where(
                StaffPushSubscription.id == delivery.subscription_id,
                StaffPushSubscription.active.is_(True),
            )
            .values(active=False, deactivated_at=now)
        )
        session.commit()
        return True
    except WebPushDeliveryFailed as error:
        delivery.status = "failed"
        delivery.error = str(error)[:500]
        session.add(delivery)
        session.commit()
        return False
    except Exception as error:  # noqa: BLE001 - one bad push must not stop the pass
        delivery.status = "failed"
        delivery.error = (str(error).strip() or error.__class__.__name__)[:500]
        session.add(delivery)
        session.commit()
        return False
    delivery.status = result.status
    delivery.error = None
    delivery.sent_at = now
    session.add(delivery)
    session.commit()
    return False


def send_pending_staff_push_deliveries(
    session: Session,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> StaffPushPass:
    """Send the oldest pending pushes, at most ``limit``.

    There is no silence window and no automatic retry here: these are the
    notices that hold the panel's work, and a failed row waits for an operator.
    """

    occurred = _as_utc(now or utc_now())
    batch = max(1, min(limit, MAX_SEND_BATCH_LIMIT))
    rows = list(
        session.exec(
            select(StaffPushDelivery)
            .where(StaffPushDelivery.status == "pending")
            .order_by(StaffPushDelivery.created_at, StaffPushDelivery.id)
            .limit(batch)
        ).all()
    )
    attempted = sent = simulated = failed = deactivated = 0
    for delivery in rows:
        if not _claim(session, delivery, from_status="pending", now=occurred):
            continue
        if _deliver(session, delivery, now=occurred):
            deactivated += 1
        attempted += 1
        if delivery.status == "sent":
            sent += 1
        elif delivery.status == "simulated":
            simulated += 1
        else:
            failed += 1
    return StaffPushPass(
        attempted=attempted,
        sent=sent,
        simulated=simulated,
        failed=failed,
        deactivated=deactivated,
        remaining=_remaining_count(session),
    )


def send_pending_staff_push_deliveries_from_engine(
    engine: Engine,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> StaffPushPass:
    """Run one pass in its own session, for the post-response hook."""

    with Session(engine) as session:
        return send_pending_staff_push_deliveries(session, limit=limit, now=now)


def retry_staff_push_delivery(
    session: Session,
    delivery_id: UUID,
    *,
    now: datetime | None = None,
) -> StaffPushDeliveryItem:
    """Attempt one failed push again, keeping its attempt history."""

    occurred = _as_utc(now or utc_now())
    delivery = session.get(StaffPushDelivery, delivery_id)
    if delivery is None:
        raise StaffPushDeliveryNotFound("No se encontró la entrega del push.")
    if delivery.status not in RETRYABLE_DELIVERY_STATUSES:
        raise StaffPushDeliveryRetryNotAllowed(
            "Solo se puede reintentar un push que falló."
        )
    if not _claim(session, delivery, from_status="failed", now=occurred):
        raise StaffPushDeliveryRetryNotAllowed(
            "Otro intento tomó esta entrega; vuelve a consultar la cola."
        )
    _deliver(session, delivery, now=occurred)
    return _delivery_item(session, delivery)


def staff_push_delivery_counts(session: Session) -> StaffPushDeliveryCounts:
    rows = session.exec(
        select(StaffPushDelivery.status, func.count())
        .group_by(StaffPushDelivery.status)
    ).all()
    by_status = {status: int(total) for status, total in rows}
    active = int(
        session.exec(
            select(func.count(StaffPushSubscription.id)).where(
                StaffPushSubscription.active.is_(True)
            )
        ).one()
        or 0
    )
    return StaffPushDeliveryCounts(
        pending=by_status.get("pending", 0),
        sent=by_status.get("sent", 0),
        simulated=by_status.get("simulated", 0),
        failed=by_status.get("failed", 0),
        active_subscriptions=active,
    )


def list_staff_push_deliveries(
    session: Session,
    *,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_DELIVERY_PAGE_SIZE,
) -> StaffPushDeliveryPage:
    """Newest attempts first, optionally filtered by status."""

    if status_filter is not None and status_filter not in DELIVERY_STATUSES:
        raise StaffPushError("El estado de la entrega no es válido.")
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    condition = (
        StaffPushDelivery.status == status_filter
        if status_filter is not None
        else None
    )
    total_query = select(func.count(StaffPushDelivery.id))
    rows_query = (
        select(StaffPushDelivery, StaffNotification, AppUser, Employee)
        .join(
            StaffNotification,
            StaffNotification.id == StaffPushDelivery.notice_id,
        )
        .join(AppUser, AppUser.id == StaffPushDelivery.user_id)
        .outerjoin(Employee, Employee.id == AppUser.employee_id)
    )
    if condition is not None:
        total_query = total_query.where(condition)
        rows_query = rows_query.where(condition)
    total = int(session.exec(total_query).one() or 0)
    rows = session.exec(
        rows_query.order_by(
            StaffPushDelivery.created_at.desc(),
            StaffPushDelivery.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return StaffPushDeliveryPage(
        items=[
            _delivery_item(
                session,
                delivery,
                notice=notice,
                user=user,
                employee=employee,
            )
            for delivery, notice, user, employee in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


def _delivery_item(
    session: Session,
    delivery: StaffPushDelivery,
    *,
    notice: StaffNotification | None = None,
    user: AppUser | None = None,
    employee: Employee | None = None,
) -> StaffPushDeliveryItem:
    if notice is None:
        notice = session.get(StaffNotification, delivery.notice_id)
    if user is None:
        user = session.get(AppUser, delivery.user_id)
    if employee is None and user is not None and user.employee_id is not None:
        employee = session.get(Employee, user.employee_id)
    name = (
        f"{employee.first_name} {employee.last_name}".strip()
        if employee is not None
        else (user.email if user is not None else "Cuenta del panel")
    )
    return StaffPushDeliveryItem(
        id=delivery.id,
        notice_id=delivery.notice_id,
        user_id=delivery.user_id,
        user_name=name,
        user_email=user.email if user is not None else "",
        kind=notice.kind if notice is not None else "workout_pending_review",
        title=notice.title if notice is not None else "Aviso del personal",
        device=mask_push_endpoint(delivery.endpoint),
        status=delivery.status,
        attempts=delivery.attempts,
        error=delivery.error,
        created_at=_as_utc(delivery.created_at),
        last_attempt_at=(
            _as_utc(delivery.last_attempt_at)
            if delivery.last_attempt_at is not None
            else None
        ),
        sent_at=(
            _as_utc(delivery.sent_at) if delivery.sent_at is not None else None
        ),
    )


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


__all__ = [
    "DEFAULT_DELIVERY_PAGE_SIZE",
    "DEFAULT_SEND_BATCH_LIMIT",
    "DELIVERY_STATUSES",
    "InvalidPushSubscription",
    "StaffPushConfig",
    "StaffPushDeliveryCounts",
    "StaffPushDeliveryItem",
    "StaffPushDeliveryNotFound",
    "StaffPushDeliveryPage",
    "StaffPushDeliveryRetryNotAllowed",
    "StaffPushError",
    "StaffPushPass",
    "StaffPushSendResult",
    "StaffPushSubscriptionItem",
    "StaffPushSubscriptionNotFound",
    "VapidConfig",
    "WebPushDeliveryFailed",
    "WebPushSubscriptionGone",
    "clean_push_endpoint",
    "deactivate_staff_push_subscription",
    "list_staff_push_deliveries",
    "list_staff_push_subscriptions",
    "mask_push_endpoint",
    "read_staff_push_config",
    "register_staff_push_subscription",
    "retry_staff_push_delivery",
    "send_pending_staff_push_deliveries",
    "send_pending_staff_push_deliveries_from_engine",
    "send_staff_web_push",
    "staff_push_delivery_counts",
    "staff_push_subscription_item",
    "vapid_config",
]
