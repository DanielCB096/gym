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
from datetime import datetime, timezone
import os
from uuid import UUID

import httpx
from sqlalchemy import func, update
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
DEFAULT_TIMEOUT_SECONDS = 15.0
DELIVERY_STATUSES = ("pending", "sent", "simulated", "failed")
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
    remaining: int


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


def _pending_count(session: Session) -> int:
    return int(
        session.exec(
            select(func.count(MemberPushDelivery.id)).where(
                MemberPushDelivery.status == "pending"
            )
        ).one()
        or 0
    )


def _claim(
    session: Session,
    delivery: MemberPushDelivery,
    *,
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
            MemberPushDelivery.status == "pending",
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
        return False
    except Exception as error:  # noqa: BLE001 - one bad push must not stop the pass
        delivery.status = "failed"
        delivery.error = (str(error).strip() or error.__class__.__name__)[:500]
        session.add(delivery)
        session.commit()
        return False
    delivery.status = status
    delivery.error = None
    delivery.sent_at = now
    session.add(delivery)
    session.commit()
    return False


def send_pending_member_push_deliveries(
    session: Session,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> MemberPushPass:
    """Send the oldest pending pushes, at most ``limit`` per pass."""

    occurred = _as_utc(now or utc_now())
    batch = max(1, min(limit, MAX_SEND_BATCH_LIMIT))
    rows = list(
        session.exec(
            select(MemberPushDelivery)
            .where(MemberPushDelivery.status == "pending")
            .order_by(MemberPushDelivery.created_at, MemberPushDelivery.id)
            .limit(batch)
        ).all()
    )
    attempted = sent = simulated = failed = deactivated = 0
    for delivery in rows:
        if not _claim(session, delivery, now=occurred):
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
    return MemberPushPass(
        attempted=attempted,
        sent=sent,
        simulated=simulated,
        failed=failed,
        deactivated=deactivated,
        remaining=_pending_count(session),
    )


def send_pending_member_push_deliveries_from_engine(
    engine: Engine,
    *,
    limit: int = DEFAULT_SEND_BATCH_LIMIT,
    now: datetime | None = None,
) -> MemberPushPass:
    """Run one pass in its own session, for the post-response hook."""

    with Session(engine) as session:
        return send_pending_member_push_deliveries(session, limit=limit, now=now)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


__all__ = [
    "DEFAULT_SEND_BATCH_LIMIT",
    "DELIVERY_STATUSES",
    "EXPO_PUSH_URL",
    "InvalidPushPlatform",
    "InvalidPushToken",
    "MemberPushPass",
    "PushDeliveryFailed",
    "PushError",
    "PushMemberNotFound",
    "PushTokenUnregistered",
    "clean_push_token",
    "deactivate_member_push_token",
    "deactivate_member_push_tokens",
    "register_member_push_token",
    "send_expo_push",
    "send_pending_member_push_deliveries",
    "send_pending_member_push_deliveries_from_engine",
]
