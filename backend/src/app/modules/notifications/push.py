"""Expo push notifications for the member app.

The member inbox only speaks when the member opens the app. A class cancellation,
a waitlist promotion or a stamped invoice are useful precisely when nobody is
looking, so each new member notice also queues one push per active device and
this module is the other half: it reads that queue **after** the domain
transaction committed, contacts Expo once per row and records the outcome.

There is no worker in this project, so the pass runs in two ways: after the
response of a request that could have queued a push (a FastAPI background task)
and on demand from the tests. Rows are claimed with a compare-and-set on
``attempts`` before the request leaves, which keeps two concurrent passes from
sending the same push twice. Preview mode simulates the delivery, exactly like
the SMTP transport, so a demo never reaches a real device.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from uuid import UUID

import httpx
from sqlalchemy import and_, func, or_, update
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.mailer import preview_mode
from app.modules.memberships.models import Member
from app.modules.notifications.models import (
    MAX_PUSH_TOKEN_CHARS,
    PUSH_PLATFORMS,
    MemberNotification,
    MemberPushDelivery,
    MemberPushToken,
    utc_now,
)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
DEFAULT_SEND_BATCH_LIMIT = 20
MAX_SEND_BATCH_LIMIT = 100
DEFAULT_DELIVERY_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 15.0
DELIVERY_STATUSES = ("pending", "sent", "simulated", "failed")
# Only a failed attempt is retried by hand; pending rows wait for the next pass.
RETRYABLE_DELIVERY_STATUSES = ("failed",)
# Attempts include the first try: one original plus two automatic retries. The
# wait grows so a short outage is ridden out without drowning Expo in traffic.
MAX_PUSH_ATTEMPTS = 3
PUSH_RETRY_BACKOFF = (timedelta(minutes=1), timedelta(minutes=5))
# A push that runs out of attempts is work nobody sees: the notice is in the
# inbox but the phone never rang. The alert goes to whoever operates the queue,
# not to the member, and it is the same permission the panel card asks for.
FAILURE_ALERT_PERMISSION = "attendance.manage"
EXPO_TOKEN_PREFIXES = ("ExponentPushToken[", "ExpoPushToken[")
UNREGISTERED_ERROR = "DeviceNotRegistered"


class PushError(Exception):
    pass


class InvalidPushToken(PushError):
    pass


class InvalidPushPlatform(PushError):
    pass


class PushMemberNotFound(PushError):
    pass


class PushDeliveryNotFound(PushError):
    pass


class PushDeliveryRetryNotAllowed(PushError):
    pass


class PushDeliveryFailed(Exception):
    """The push service rejected the message or could not be reached."""


class PushTokenUnregistered(PushDeliveryFailed):
    """Expo says the app is no longer installed; the token is retired."""


@dataclass(frozen=True)
class MemberPushPass:
    """What one send pass did to the queue."""

    attempted: int
    sent: int
    simulated: int
    failed: int
    deactivated: int
    retried: int
    remaining: int


@dataclass(frozen=True)
class MemberPushDeliveryItem:
    """One queued push as the panel shows it, with the token masked."""

    id: UUID
    notification_id: UUID
    member_id: UUID
    member_name: str
    member_email: str | None
    kind: str
    title: str
    device: str
    status: str
    attempts: int
    error: str | None
    created_at: datetime
    last_attempt_at: datetime | None
    next_attempt_at: datetime | None
    sent_at: datetime | None


@dataclass(frozen=True)
class MemberPushDeliveryPage:
    items: list[MemberPushDeliveryItem]
    total: int
    page: int
    page_size: int
    pages: int
    max_attempts: int


@dataclass(frozen=True)
class MemberPushDeliveryCounts:
    pending: int
    sent: int
    simulated: int
    failed: int
    active_tokens: int


def clean_push_token(raw: str) -> str:
    """Accept only the token shape Expo hands to the app."""

    token = (raw or "").strip()
    prefix = next(
        (candidate for candidate in EXPO_TOKEN_PREFIXES if token.startswith(candidate)),
        None,
    )
    inner = token[len(prefix) : -1] if prefix is not None and token.endswith("]") else ""
    if (
        prefix is None
        or not inner
        or len(token) > MAX_PUSH_TOKEN_CHARS
        or not all(char.isalnum() or char in "-_" for char in inner)
    ):
        raise InvalidPushToken(
            "El token de notificaciones no tiene el formato de Expo Push."
        )
    return token


def register_member_push_token(
    session: Session,
    member_id: UUID,
    *,
    token: str,
    platform: str,
    now: datetime | None = None,
) -> MemberPushToken:
    """Attach a device to the member, transferring it if it belonged to another.

    The same installation may sign in with another account later; the token
    follows the account that registered it last instead of leaving the previous
    member receiving the new one's notices.
    """

    clean_token = clean_push_token(token)
    clean_platform = (platform or "").strip().lower()
    if clean_platform not in PUSH_PLATFORMS:
        raise InvalidPushPlatform("La plataforma debe ser 'ios' o 'android'.")
    if session.get(Member, member_id) is None:
        raise PushMemberNotFound("El socio no existe")

    occurred = _as_utc(now or utc_now())
    row = session.exec(
        select(MemberPushToken).where(MemberPushToken.token == clean_token)
    ).first()
    if row is None:
        row = MemberPushToken(
            member_id=member_id,
            token=clean_token,
            platform=clean_platform,
            created_at=occurred,
            last_seen_at=occurred,
        )
    else:
        row.member_id = member_id
        row.platform = clean_platform
        row.active = True
        row.deactivated_at = None
        row.last_seen_at = occurred
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def deactivate_member_push_token(
    session: Session,
    member_id: UUID,
    token: str,
    *,
    now: datetime | None = None,
) -> bool:
    occurred = _as_utc(now or utc_now())
    row = session.exec(
        select(MemberPushToken).where(MemberPushToken.token == (token or "").strip())
    ).first()
    if row is None or row.member_id != member_id or not row.active:
        return False
    row.active = False
    row.deactivated_at = occurred
    session.add(row)
    session.commit()
    return True


def deactivate_member_push_tokens(
    session: Session,
    member_id: UUID,
    *,
    now: datetime | None = None,
) -> int:
    """Silence every device of the member, for the logout path."""

    occurred = _as_utc(now or utc_now())
    result = session.exec(
        update(MemberPushToken)
        .where(
            MemberPushToken.member_id == member_id,
            MemberPushToken.active.is_(True),
        )
        .values(active=False, deactivated_at=occurred)
    )
    session.commit()
    return int(result.rowcount or 0)


def send_expo_push(
    *, token: str, title: str, body: str, data: dict[str, str]
) -> str:
    """Send one message and return ``sent``; preview mode returns ``simulated``."""

    if preview_mode():
        return "simulated"
    try:
        timeout = float(
            os.getenv("EXPO_PUSH_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
        )
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    try:
        response = httpx.post(
            EXPO_PUSH_URL,
            json=[
                {
                    "to": token,
                    "title": title,
                    "body": body,
                    "sound": "default",
                    "data": data,
                }
            ],
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as error:
        raise PushDeliveryFailed(
            f"No se pudo contactar al servicio de notificaciones: {error}"
        ) from error
    if response.status_code >= 400:
        raise PushDeliveryFailed(
            f"El servicio de notificaciones respondió {response.status_code}."
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise PushDeliveryFailed(
            "El servicio de notificaciones devolvió una respuesta ilegible."
        ) from error

    ticket = _ticket(payload)
    if ticket["status"] == "ok":
        return "sent"
    if ticket["code"] == UNREGISTERED_ERROR:
        raise PushTokenUnregistered(
            "La app ya no está instalada en el dispositivo; se retiró el token."
        )
    raise PushDeliveryFailed(ticket["message"] or "El servicio rechazó la notificación.")


def _ticket(payload: object) -> dict[str, str | None]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise PushDeliveryFailed(
            "El servicio de notificaciones no devolvió el estado del envío."
        )
    details = data.get("details")
    code = details.get("error") if isinstance(details, dict) else None
    message = data.get("message")
    return {
        "status": str(data.get("status") or ""),
        "code": code if isinstance(code, str) else None,
        "message": message if isinstance(message, str) else None,
    }


def _remaining_count(session: Session) -> int:
    """Rows a later pass still has work for: untouched or waiting to retry."""

    return int(
        session.exec(
            select(func.count(MemberPushDelivery.id)).where(
                or_(
                    MemberPushDelivery.status == "pending",
                    and_(
                        MemberPushDelivery.status == "failed",
                        MemberPushDelivery.attempts < MAX_PUSH_ATTEMPTS,
                        MemberPushDelivery.next_attempt_at.is_not(None),
                    ),
                )
            )
        ).one()
        or 0
    )


def _claim(
    session: Session,
    delivery: MemberPushDelivery,
    *,
    from_status: str,
    now: datetime,
) -> bool:
    """Count the attempt and commit it before the request leaves.

    The compare-and-set on ``attempts`` makes a second concurrent pass lose the
    claim and skip the row instead of pushing the same notice twice.
    """

    result = session.exec(
        update(MemberPushDelivery)
        .where(
            MemberPushDelivery.id == delivery.id,
            MemberPushDelivery.status == from_status,
            MemberPushDelivery.attempts == delivery.attempts,
        )
        .values(
            attempts=MemberPushDelivery.attempts + 1,
            last_attempt_at=now,
        )
    )
    session.commit()
    if not result.rowcount:
        session.refresh(delivery)
        return False
    session.refresh(delivery)
    return True


def _deactivate_token(
    session: Session, *, member_id: UUID, token: str, now: datetime
) -> None:
    session.exec(
        update(MemberPushToken)
        .where(
            MemberPushToken.member_id == member_id,
            MemberPushToken.token == token,
            MemberPushToken.active.is_(True),
        )
        .values(active=False, deactivated_at=now)
    )


def _deliver(
    session: Session, delivery: MemberPushDelivery, *, now: datetime
) -> bool:
    """Send one claimed push; return whether the token was retired."""

    notice = session.get(MemberNotification, delivery.notification_id)
    if notice is None:
        # The foreign key makes this unreachable; if it ever happens the row
        # must not stay pending forever.
        delivery.status = "failed"
        delivery.error = "El aviso de la notificación ya no existe."
        delivery.next_attempt_at = None
        session.add(delivery)
        session.commit()
        return False
    data = {"notification_id": str(notice.id), "kind": notice.kind}
    if notice.ref_id is not None:
        data["ref_id"] = str(notice.ref_id)
    try:
        status = send_expo_push(
            token=delivery.token,
            title=notice.title,
            body=notice.body,
            data=data,
        )
    except PushTokenUnregistered as error:
        delivery.status = "failed"
        delivery.error = str(error)[:500]
        delivery.next_attempt_at = None
        session.add(delivery)
        _deactivate_token(
            session,
            member_id=delivery.member_id,
            token=delivery.token,
            now=now,
        )
        session.commit()
        return True
    except PushDeliveryFailed as error:
        delivery.status = "failed"
        delivery.error = str(error)[:500]
        session.add(delivery)
        session.commit()
        _schedule_retry(session, delivery, now=now)
        return False
    except Exception as error:  # noqa: BLE001 - one bad push must not stop the pass
        delivery.status = "failed"
        delivery.error = (str(error).strip() or error.__class__.__name__)[:500]
        session.add(delivery)
        session.commit()
        _schedule_retry(session, delivery, now=now)
        return False
    delivery.status = status
    delivery.error = None
    delivery.next_attempt_at = None
    delivery.sent_at = now
    session.add(delivery)
    session.commit()
    return False


def _schedule_retry(
    session: Session,
    delivery: MemberPushDelivery,
    *,
    now: datetime,
) -> None:
    """Queue the next automatic attempt while attempts remain."""

    if delivery.attempts >= MAX_PUSH_ATTEMPTS:
        delivery.next_attempt_at = None
        session.add(delivery)
        session.commit()
        _alert_exhausted_push(session, delivery, now=now)
        return
    delay = PUSH_RETRY_BACKOFF[
        min(delivery.attempts - 1, len(PUSH_RETRY_BACKOFF) - 1)
    ]
    delivery.next_attempt_at = now + delay
    session.add(delivery)
    session.commit()


def _alert_exhausted_push(
    session: Session,
    delivery: MemberPushDelivery,
    *,
    now: datetime,
) -> None:
    """Tell the accounts that operate the queue that the push gave up.

    The key names the delivery *and* the account, so the notice is written once
    per pair: a manual retry that fails again does not repeat it, and a new
    device row for the same notice is a separate failure with its own alert.
    """

    # Late imports: the identity and inbox services sit above this module.
    from app.modules.identity.service import user_ids_with_permission
    from app.modules.notifications.service import create_staff_notification

    notice = session.get(MemberNotification, delivery.notification_id)
    member = session.get(Member, delivery.member_id)
    who = (
        f"{member.first_name} {member.last_name}".strip()
        if member is not None
        else "Un socio"
    )
    label = _clip(notice.title if notice is not None else "un aviso", 80)
    reason = _clip(delivery.error or "sin detalle", 160).rstrip(".")
    body = (
        f"No se pudo entregar el aviso «{label}» a {_clip(who, 60)} tras "
        f"{delivery.attempts} intentos: {reason}. "
        "Revísalo en la tarjeta «Push del socio» de la pestaña Equipo."
    )
    for user_id in user_ids_with_permission(
        session, FAILURE_ALERT_PERMISSION, now=now
    ):
        create_staff_notification(
            session,
            user_id=user_id,
            kind="member_push_failed",
            title="Push del socio sin entregar",
            body=body,
            ref_id=delivery.id,
            dedupe_key=f"member_push_failed:{delivery.id}:{user_id}",
            now=now,
        )
    session.commit()


def _clip(value: str, limit: int) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _retry_due(now: datetime):
    """A failed row whose automatic retry is already due."""

    return and_(
        MemberPushDelivery.status == "failed",
        MemberPushDelivery.attempts < MAX_PUSH_ATTEMPTS,
        MemberPushDelivery.next_attempt_at.is_not(None),
        MemberPushDelivery.next_attempt_at <= now,
    )


def send_pending_member_push_deliveries(
    session: Session,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> MemberPushPass:
    """Send the oldest pending pushes and the retries that are due, at most ``limit``."""

    occurred = _as_utc(now or utc_now())
    batch = max(1, min(limit, MAX_SEND_BATCH_LIMIT))
    rows = list(
        session.exec(
            select(MemberPushDelivery)
            .where(
                or_(
                    MemberPushDelivery.status == "pending",
                    _retry_due(occurred),
                )
            )
            .order_by(MemberPushDelivery.created_at, MemberPushDelivery.id)
            .limit(batch)
        ).all()
    )
    attempted = sent = simulated = failed = deactivated = retried = 0
    for delivery in rows:
        was_failed = delivery.status == "failed"
        if not _claim(
            session, delivery, from_status=delivery.status, now=occurred
        ):
            continue
        if was_failed:
            retried += 1
        if _deliver(session, delivery, now=occurred):
            deactivated += 1
        attempted += 1
        if delivery.status == "sent":
            sent += 1
        elif delivery.status == "simulated":
            simulated += 1
        else:
            failed += 1
    return MemberPushPass(
        attempted=attempted,
        sent=sent,
        simulated=simulated,
        failed=failed,
        deactivated=deactivated,
        retried=retried,
        remaining=_remaining_count(session),
    )


def send_pending_member_push_deliveries_from_engine(
    engine: Engine,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> MemberPushPass:
    """Run one pass in its own session, for the post-response hook.

    An exhausted push writes staff notices and queues their emails; the same
    hook drains that queue, because no later request is guaranteed to flush it.
    """

    with Session(engine) as session:
        result = send_pending_member_push_deliveries(session, limit=limit, now=now)
    # Late import: the email half of the same package, which this module only
    # needs after a push has given up.
    from app.modules.notifications.delivery import (
        send_pending_staff_notification_emails_from_engine,
    )

    send_pending_staff_notification_emails_from_engine(engine)
    return result


def mask_push_token(token: str) -> str:
    """Keep the last four characters; the panel never needs the whole token."""

    inner = token
    if "[" in token and token.endswith("]"):
        inner = token[token.index("[") + 1 : -1]
    return f"…{inner[-4:]}" if len(inner) > 4 else "…"


def retry_member_push_delivery(
    session: Session,
    delivery_id: UUID,
    *,
    now: datetime | None = None,
) -> MemberPushDeliveryItem:
    """Attempt one failed push again, keeping its attempt history."""

    occurred = _as_utc(now or utc_now())
    delivery = session.get(MemberPushDelivery, delivery_id)
    if delivery is None:
        raise PushDeliveryNotFound("No se encontró la entrega del push.")
    if delivery.status not in RETRYABLE_DELIVERY_STATUSES:
        raise PushDeliveryRetryNotAllowed(
            "Solo se puede reintentar un push que falló."
        )
    if not _claim(session, delivery, from_status="failed", now=occurred):
        raise PushDeliveryRetryNotAllowed(
            "Otro intento tomó esta entrega; vuelve a consultar la cola."
        )
    _deliver(session, delivery, now=occurred)
    return _delivery_item(session, delivery)


def member_push_delivery_counts(session: Session) -> MemberPushDeliveryCounts:
    rows = session.exec(
        select(MemberPushDelivery.status, func.count())
        .group_by(MemberPushDelivery.status)
    ).all()
    by_status = {status: int(total) for status, total in rows}
    active_tokens = int(
        session.exec(
            select(func.count(MemberPushToken.id)).where(
                MemberPushToken.active.is_(True)
            )
        ).one()
        or 0
    )
    return MemberPushDeliveryCounts(
        pending=by_status.get("pending", 0),
        sent=by_status.get("sent", 0),
        simulated=by_status.get("simulated", 0),
        failed=by_status.get("failed", 0),
        active_tokens=active_tokens,
    )


def list_member_push_deliveries(
    session: Session,
    *,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_DELIVERY_PAGE_SIZE,
) -> MemberPushDeliveryPage:
    """Newest attempts first, optionally filtered by status."""

    if status_filter is not None and status_filter not in DELIVERY_STATUSES:
        raise PushError("El estado de la entrega no es válido.")
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    condition = (
        MemberPushDelivery.status == status_filter
        if status_filter is not None
        else None
    )
    total_query = select(func.count(MemberPushDelivery.id))
    rows_query = (
        select(MemberPushDelivery, MemberNotification, Member)
        .join(
            MemberNotification,
            MemberNotification.id == MemberPushDelivery.notification_id,
        )
        .join(Member, Member.id == MemberPushDelivery.member_id)
    )
    if condition is not None:
        total_query = total_query.where(condition)
        rows_query = rows_query.where(condition)
    total = int(session.exec(total_query).one() or 0)
    rows = session.exec(
        rows_query.order_by(
            MemberPushDelivery.created_at.desc(),
            MemberPushDelivery.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return MemberPushDeliveryPage(
        items=[
            _delivery_item(session, delivery, notice=notice, member=member)
            for delivery, notice, member in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        max_attempts=MAX_PUSH_ATTEMPTS,
    )


def _delivery_item(
    session: Session,
    delivery: MemberPushDelivery,
    *,
    notice: MemberNotification | None = None,
    member: Member | None = None,
) -> MemberPushDeliveryItem:
    if notice is None:
        notice = session.get(MemberNotification, delivery.notification_id)
    if member is None:
        member = session.get(Member, delivery.member_id)
    name = (
        f"{member.first_name} {member.last_name}".strip()
        if member is not None
        else "Socio"
    )
    return MemberPushDeliveryItem(
        id=delivery.id,
        notification_id=delivery.notification_id,
        member_id=delivery.member_id,
        member_name=name,
        member_email=member.email if member is not None else None,
        kind=notice.kind if notice is not None else "class_reserved",
        title=notice.title if notice is not None else "Aviso al socio",
        device=mask_push_token(delivery.token),
        status=delivery.status,
        attempts=delivery.attempts,
        error=delivery.error,
        created_at=_as_utc(delivery.created_at),
        last_attempt_at=(
            _as_utc(delivery.last_attempt_at)
            if delivery.last_attempt_at is not None
            else None
        ),
        next_attempt_at=(
            _as_utc(delivery.next_attempt_at)
            if delivery.next_attempt_at is not None
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
    "EXPO_PUSH_URL",
    "FAILURE_ALERT_PERMISSION",
    "InvalidPushPlatform",
    "InvalidPushToken",
    "MAX_PUSH_ATTEMPTS",
    "MemberPushDeliveryCounts",
    "MemberPushDeliveryItem",
    "MemberPushDeliveryPage",
    "MemberPushPass",
    "PUSH_RETRY_BACKOFF",
    "PushDeliveryFailed",
    "PushDeliveryNotFound",
    "PushDeliveryRetryNotAllowed",
    "PushError",
    "PushMemberNotFound",
    "PushTokenUnregistered",
    "RETRYABLE_DELIVERY_STATUSES",
    "clean_push_token",
    "deactivate_member_push_token",
    "deactivate_member_push_tokens",
    "list_member_push_deliveries",
    "mask_push_token",
    "member_push_delivery_counts",
    "register_member_push_token",
    "retry_member_push_delivery",
    "send_expo_push",
    "send_pending_member_push_deliveries",
    "send_pending_member_push_deliveries_from_engine",
]
