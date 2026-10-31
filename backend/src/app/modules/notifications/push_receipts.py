"""Receipts for the pushes Expo accepted.

``sent`` means Expo took the message; it cannot know whether the phone got it.
That answer arrives later as a receipt tied to the ticket Expo returned from the
send. There is no webhook for this half — Expo exposes receipts through a pull
API — so a pass reads the tickets the queue kept and stores one receipt per
delivery, exactly like the staff email receipts of ADR-051 but pulled instead of
pushed. The delivery status is never rewritten: the receipt is information
beside the queue.

Expo keeps a receipt for 24 hours. A ticket that old without an answer is
recorded as ``expired`` instead of being asked forever, and a ticket answered
"not yet" is asked again only after a wait, because a tight loop would spend
requests without moving the answer. Preview mode never queues a ticket, so a
demo has nothing to ask about and the pass returns ``deferred``.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os

import httpx
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.mailer import preview_mode
from app.modules.notifications.models import (
    MemberPushDelivery,
    MemberPushDeliveryReceipt,
    MemberPushToken,
    utc_now,
)

EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_RECEIPT_BATCH = 200
# Expo accepts at most 1000 ticket ids in one call.
MAX_RECEIPT_BATCH = 1000
# Expo stops answering a ticket after 24 hours.
RECEIPT_EXPIRY = timedelta(hours=24)
# Receipts usually lag the send by seconds; asking again sooner than this
# without an answer only spends requests.
RECEIPT_RECHECK = timedelta(minutes=15)
UNREGISTERED_ERROR = "DeviceNotRegistered"
MAX_DETAIL_CHARS = 500


class PushReceiptsFailed(Exception):
    """Expo could not be reached or answered with an unreadable body."""


@dataclass(frozen=True)
class ExpoReceipt:
    """One ticket's answer: ``ok`` or ``error`` with its code and message."""

    status: str
    code: str | None
    message: str | None


@dataclass(frozen=True)
class PushReceiptPass:
    """What one pass did with the tickets that had no receipt yet."""

    checked: int
    delivered: int
    errors: int
    expired: int
    deactivated: int
    pending: int
    deferred: bool = False


def fetch_expo_receipts(ticket_ids: list[str]) -> dict[str, ExpoReceipt]:
    """Ask Expo about the tickets and keep the answers it actually returned.

    A ticket missing from the answer has no receipt yet and is left for a later
    pass; that is not an error.
    """

    if not ticket_ids:
        return {}
    try:
        response = httpx.post(
            EXPO_RECEIPTS_URL,
            json={"ids": ticket_ids},
            timeout=_timeout(),
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as error:
        raise PushReceiptsFailed(
            f"No se pudo consultar los acuses: {error}"
        ) from error
    if response.status_code >= 400:
        raise PushReceiptsFailed(
            "El servicio de notificaciones respondió "
            f"{response.status_code} al consultar los acuses."
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise PushReceiptsFailed(
            "El servicio de notificaciones devolvió acuses ilegibles."
        ) from error
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise PushReceiptsFailed(
            "El servicio de notificaciones no devolvió los acuses."
        )
    receipts: dict[str, ExpoReceipt] = {}
    for ticket_id, entry in data.items():
        if not isinstance(ticket_id, str) or not isinstance(entry, dict):
            continue
        details = entry.get("details")
        code = details.get("error") if isinstance(details, dict) else None
        message = entry.get("message")
        receipts[ticket_id] = ExpoReceipt(
            status=str(entry.get("status") or ""),
            code=code if isinstance(code, str) else None,
            message=message if isinstance(message, str) else None,
        )
    return receipts


def sync_member_push_receipts(
    session: Session,
    *,
    limit: int = DEFAULT_RECEIPT_BATCH,
    now: datetime | None = None,
) -> PushReceiptPass:
    """Store the receipts of the sent pushes Expo already answers for.

    The pass is safe to repeat: a delivery with a receipt is never asked again,
    an unanswered ticket waits ``RECEIPT_RECHECK`` before the next question, and
    the receipt's unique keys make a concurrent pass store the same answer once.
    """

    occurred = _as_utc(now or utc_now())
    if preview_mode():
        return PushReceiptPass(
            checked=0,
            delivered=0,
            errors=0,
            expired=0,
            deactivated=0,
            pending=_pending_count(session),
            deferred=True,
        )

    batch = max(1, min(limit, MAX_RECEIPT_BATCH))
    rows = list(
        session.exec(
            select(MemberPushDelivery)
            .outerjoin(
                MemberPushDeliveryReceipt,
                MemberPushDeliveryReceipt.delivery_id == MemberPushDelivery.id,
            )
            .where(
                MemberPushDelivery.status == "sent",
                MemberPushDelivery.expo_ticket_id.is_not(None),
                MemberPushDeliveryReceipt.id.is_(None),
                or_(
                    MemberPushDelivery.receipt_checked_at.is_(None),
                    MemberPushDelivery.receipt_checked_at
                    <= occurred - RECEIPT_RECHECK,
                ),
            )
            .order_by(MemberPushDelivery.sent_at, MemberPushDelivery.id)
            .limit(batch)
        ).all()
    )

    delivered = errors = expired = deactivated = 0
    askable: list[MemberPushDelivery] = []
    for delivery in rows:
        sent_at = delivery.sent_at
        if sent_at is not None and _as_utc(sent_at) <= occurred - RECEIPT_EXPIRY:
            # Expo no longer keeps the answer: waiting would never end.
            _store(
                session,
                delivery,
                status="expired",
                detail="Expo ya no conserva el acuse (24 horas).",
                now=occurred,
            )
            expired += 1
        else:
            askable.append(delivery)

    if askable:
        answers = fetch_expo_receipts(
            [delivery.expo_ticket_id or "" for delivery in askable]
        )
        for delivery in askable:
            answer = answers.get(delivery.expo_ticket_id or "")
            if answer is None:
                delivery.receipt_checked_at = occurred
                session.add(delivery)
                continue
            if answer.status == "ok":
                _store(session, delivery, status="ok", detail=None, now=occurred)
                delivered += 1
                continue
            _store(
                session,
                delivery,
                status="error",
                detail=_detail(answer),
                now=occurred,
            )
            errors += 1
            if answer.code == UNREGISTERED_ERROR:
                deactivated += _retire_token(session, delivery, now=occurred)
    session.commit()

    return PushReceiptPass(
        checked=len(rows),
        delivered=delivered,
        errors=errors,
        expired=expired,
        deactivated=deactivated,
        pending=_pending_count(session),
    )


def _pending_count(session: Session) -> int:
    """Sent pushes whose ticket still has no receipt."""

    return int(
        session.exec(
            select(func.count(MemberPushDelivery.id))
            .outerjoin(
                MemberPushDeliveryReceipt,
                MemberPushDeliveryReceipt.delivery_id == MemberPushDelivery.id,
            )
            .where(
                MemberPushDelivery.status == "sent",
                MemberPushDelivery.expo_ticket_id.is_not(None),
                MemberPushDeliveryReceipt.id.is_(None),
            )
        ).one()
        or 0
    )


def _store(
    session: Session,
    delivery: MemberPushDelivery,
    *,
    status: str,
    detail: str | None,
    now: datetime,
) -> None:
    receipt = MemberPushDeliveryReceipt(
        delivery_id=delivery.id,
        ticket_id=delivery.expo_ticket_id or "",
        status=status,
        detail=detail[:MAX_DETAIL_CHARS] if detail else None,
        received_at=now,
    )
    delivery.receipt_checked_at = now
    session.add(delivery)
    session.add(receipt)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        # Another pass stored this ticket's answer first; one row wins.
        session.expunge(receipt)


def _retire_token(
    session: Session, delivery: MemberPushDelivery, *, now: datetime
) -> int:
    """Retire the device Expo says is gone, if it is still active."""

    result = session.exec(
        update(MemberPushToken)
        .where(
            MemberPushToken.member_id == delivery.member_id,
            MemberPushToken.token == delivery.token,
            MemberPushToken.active.is_(True),
        )
        .values(active=False, deactivated_at=now)
    )
    return int(result.rowcount or 0)


def _detail(answer: ExpoReceipt) -> str:
    code = (answer.code or "").strip()
    message = (answer.message or "").strip()
    if code and message:
        return f"{code}: {message}"
    return code or message or "El servicio reportó un error al entregar el aviso."


def _timeout() -> float:
    try:
        return float(os.getenv("EXPO_PUSH_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


__all__ = [
    "DEFAULT_RECEIPT_BATCH",
    "EXPO_RECEIPTS_URL",
    "ExpoReceipt",
    "MAX_RECEIPT_BATCH",
    "PushReceiptPass",
    "PushReceiptsFailed",
    "RECEIPT_EXPIRY",
    "RECEIPT_RECHECK",
    "fetch_expo_receipts",
    "sync_member_push_receipts",
]
