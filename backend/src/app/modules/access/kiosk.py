"""Member check-in with rotating codes and a reception kiosk.

The member app asks the backend for a six-digit code, shows it on screen for a
few minutes, and the tablet at the front desk validates it. The kiosk is
provisioned with its own token so it never holds a staff session, and every
decision reuses :func:`evaluate_access` and lands in the same access log as the
manual and reader entries.

Codes are stored only as an HMAC digest, expire after five minutes, are
single-use, and a new code invalidates the previous ones. Attempts are limited
per device so a six-digit space cannot be brute-forced from the tablet.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import hmac
import os
import re
import secrets
from uuid import UUID, uuid4

from sqlalchemy import func, update
from sqlmodel import Session, select

from app.modules.access.models import (
    AccessDirection,
    AccessRequest,
    AccessSnapshot,
    KioskAttempt,
    KioskDevice,
    MemberAccessCode,
    utc_now,
)
from app.modules.access.service import evaluate_access, record_access_event
from app.modules.memberships.models import Member, Membership
from app.modules.portal.service import signing_secret
from app.timezone import DEFAULT_TIMEZONE

ACCESS_CODE_LIFETIME = timedelta(minutes=5)
ACCESS_CODE_REQUEST_WINDOW = timedelta(minutes=10)
ACCESS_CODE_MAX_REQUESTS = 6
KIOSK_ATTEMPT_WINDOW = timedelta(minutes=1)
KIOSK_ATTEMPT_LIMIT = 10
LAST_SEEN_REFRESH = timedelta(minutes=1)

REASON_MESSAGES: dict[str, str] = {
    "entry_allowed": "Acceso concedido",
    "membership_not_active": "Membresía no activa. Pasa a recepción.",
    "membership_not_started": "Tu membresía aún no inicia.",
    "membership_expired": "Membresía vencida. Pasa a recepción.",
    "snapshot_missing": "No hay una membresía registrada.",
    "blocking_debt": "Tienes un adeudo pendiente. Pasa a recepción.",
    "outside_allowed_hours": "Estás fuera del horario permitido.",
    "daily_limit": "Ya usaste tus entradas de hoy.",
    "antipassback": "Entrada duplicada. Espera un momento.",
    "occupancy_full": "El club está lleno en este momento.",
}


class KioskError(Exception):
    pass


class InvalidKioskToken(KioskError):
    pass


class KioskDeviceNotFound(KioskError):
    pass


class InvalidKioskLabel(KioskError):
    pass


class MemberAccessUnavailable(KioskError):
    pass


class AccessCodeRateLimited(KioskError):
    pass


class InvalidAccessCode(KioskError):
    pass


class KioskRateLimited(KioskError):
    pass


@dataclass(frozen=True)
class AccessCodeResult:
    code: str
    expires_at: datetime
    expires_in_seconds: int


@dataclass(frozen=True)
class KioskCheckInResult:
    authorized: bool
    reason: str
    message: str
    member_name: str | None
    reader_id: str
    occurred_at: datetime
    event_id: UUID


@dataclass(frozen=True)
class KioskEquipmentNotice:
    name: str
    location: str | None
    status: str
    status_label: str


EQUIPMENT_STATUS_MESSAGES: dict[str, str] = {
    "maintenance": "En mantenimiento",
    "out_of_service": "Fuera de servicio",
}


def list_kiosk_equipment_notices(session: Session) -> list[KioskEquipmentNotice]:
    # Imported lazily: the access module never imports maintenance on load, so
    # the kiosk keeps its own dependency graph (same rule as notices).
    from app.modules.maintenance.service import list_unavailable_equipment

    return [
        KioskEquipmentNotice(
            name=item.name,
            location=item.location,
            status=item.status,
            status_label=EQUIPMENT_STATUS_MESSAGES.get(item.status, item.status),
        )
        for item in list_unavailable_equipment(session)
    ]


def issue_member_access_code(
    session: Session,
    member_id: UUID,
    *,
    now: datetime | None = None,
) -> AccessCodeResult:
    occurred_at = _as_utc(now or utc_now())
    member = session.get(Member, member_id)
    membership = _latest_membership(session, member_id)
    if member is None or not _membership_active(member, membership, occurred_at):
        raise MemberAccessUnavailable(
            "Tu membresía no está activa. Pasa a recepción para regularizarla."
        )

    window_start = occurred_at - ACCESS_CODE_REQUEST_WINDOW
    recent = session.exec(
        select(func.count(MemberAccessCode.id)).where(
            MemberAccessCode.member_id == member_id,
            MemberAccessCode.created_at >= window_start,
        )
    ).one()
    if int(recent or 0) >= ACCESS_CODE_MAX_REQUESTS:
        raise AccessCodeRateLimited(
            "Pediste varios códigos seguidos. Espera unos minutos e intenta de nuevo."
        )

    session.exec(
        update(MemberAccessCode)
        .where(
            MemberAccessCode.member_id == member_id,
            MemberAccessCode.consumed_at.is_(None),
        )
        .values(consumed_at=occurred_at)
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = occurred_at + ACCESS_CODE_LIFETIME
    session.add(
        MemberAccessCode(
            member_id=member_id,
            code_hash=_access_code_hash(code),
            created_at=occurred_at,
            expires_at=expires_at,
        )
    )
    session.commit()
    return AccessCodeResult(
        code=code,
        expires_at=expires_at,
        expires_in_seconds=int(ACCESS_CODE_LIFETIME.total_seconds()),
    )


def create_kiosk_device(
    session: Session,
    *,
    label: str,
    created_by: UUID | None = None,
) -> tuple[KioskDevice, str]:
    cleaned = label.strip()
    if not cleaned or len(cleaned) > 80:
        raise InvalidKioskLabel("El nombre del kiosco debe tener entre 1 y 80 caracteres.")
    raw_token = secrets.token_urlsafe(32)
    device = KioskDevice(
        label=cleaned,
        token_sha256=_token_hash(raw_token),
        created_by=created_by,
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device, raw_token


def list_kiosk_devices(session: Session) -> list[KioskDevice]:
    return list(
        session.exec(
            select(KioskDevice).order_by(KioskDevice.created_at.desc())
        ).all()
    )


def revoke_kiosk_device(
    session: Session,
    device_id: UUID,
    *,
    now: datetime | None = None,
) -> KioskDevice:
    device = session.get(KioskDevice, device_id)
    if device is None:
        raise KioskDeviceNotFound("El kiosco no existe.")
    if device.status != "revoked":
        device.status = "revoked"
        session.add(device)
        session.commit()
        session.refresh(device)
    return device


def authenticate_kiosk_device(
    session: Session,
    token: str,
    *,
    now: datetime | None = None,
) -> KioskDevice:
    occurred_at = _as_utc(now or utc_now())
    device = session.exec(
        select(KioskDevice).where(
            KioskDevice.token_sha256 == _token_hash(token),
            KioskDevice.status == "active",
        )
    ).first()
    if device is None:
        raise InvalidKioskToken("El kiosco no está autorizado.")
    last_seen = device.last_seen_at
    if last_seen is None or _as_utc(last_seen) <= occurred_at - LAST_SEEN_REFRESH:
        device.last_seen_at = occurred_at
        session.add(device)
        session.commit()
    return device


def check_in_with_code(
    session: Session,
    *,
    device: KioskDevice,
    code: str,
    now: datetime | None = None,
) -> KioskCheckInResult:
    occurred_at = _as_utc(now or utc_now())
    window_start = occurred_at - KIOSK_ATTEMPT_WINDOW
    attempts = session.exec(
        select(func.count(KioskAttempt.id)).where(
            KioskAttempt.device_id == device.id,
            KioskAttempt.occurred_at >= window_start,
        )
    ).one()
    if int(attempts or 0) >= KIOSK_ATTEMPT_LIMIT:
        raise KioskRateLimited("Demasiados intentos seguidos. Espera un minuto.")

    normalized = code.strip()
    if not re.fullmatch(r"\d{6}", normalized):
        _record_attempt(session, device.id, "invalid", occurred_at)
        raise InvalidAccessCode("Código inválido o vencido.")

    access_code = session.exec(
        select(MemberAccessCode)
        .where(
            MemberAccessCode.code_hash == _access_code_hash(normalized),
            MemberAccessCode.consumed_at.is_(None),
            MemberAccessCode.expires_at > occurred_at,
        )
        .order_by(MemberAccessCode.created_at.desc())
    ).first()
    member = (
        session.get(Member, access_code.member_id) if access_code is not None else None
    )
    if access_code is None or member is None:
        _record_attempt(session, device.id, "invalid", occurred_at)
        raise InvalidAccessCode("Código inválido o vencido.")

    consumed = session.exec(
        update(MemberAccessCode)
        .where(
            MemberAccessCode.id == access_code.id,
            MemberAccessCode.consumed_at.is_(None),
        )
        .values(consumed_at=occurred_at)
    )
    if consumed.rowcount != 1:
        session.rollback()
        _record_attempt(session, device.id, "invalid", occurred_at)
        raise InvalidAccessCode("Código inválido o vencido.")

    reader_id = f"Kiosco {device.label}"[:80]
    decision = _decide(session, member, occurred_at, reader_id)
    record_access_event(session, decision, reader_id=reader_id, source="reader")
    _record_attempt(
        session,
        device.id,
        "authorized" if decision.authorized else "denied",
        occurred_at,
    )
    return KioskCheckInResult(
        authorized=decision.authorized,
        reason=decision.reason.value,
        message=REASON_MESSAGES.get(decision.reason.value, "Acceso no disponible."),
        member_name=f"{member.first_name} {member.last_name[:1]}.".strip(),
        reader_id=reader_id,
        occurred_at=decision.occurred_at,
        event_id=decision.event_id,
    )


def _decide(
    session: Session,
    member: Member,
    occurred_at: datetime,
    reader_id: str,
):
    membership = _latest_membership(session, member.id)
    snapshot = None
    if membership is not None:
        snapshot = AccessSnapshot(
            member_id=member.id,
            membership_status=(
                membership.status if member.status == "active" else "inactive"
            ),
            membership_starts_at=_as_utc(membership.starts_at),
            membership_ends_at=_as_utc(membership.ends_at),
            blocking_debt=False,
            cached_at=occurred_at,
            valid_until=occurred_at + KIOSK_ATTEMPT_WINDOW,
            allowed_windows=None,
            daily_entry_limit=None,
            entries_today=0,
            antipassback_seconds=0,
        )
    request = AccessRequest(
        event_id=uuid4(),
        member_id=member.id,
        reader_id=reader_id,
        direction=AccessDirection.ENTRY,
        occurred_at=occurred_at,
        # Occupancy, schedules and debt blocking are not wired yet; the kiosk
        # only enforces membership state until those policies exist.
        current_occupancy=0,
        max_occupancy=1,
        offline=False,
    )
    return evaluate_access(
        snapshot,
        request,
        timezone_name=os.getenv("APP_TIMEZONE", DEFAULT_TIMEZONE),
    )


def _membership_active(
    member: Member,
    membership: Membership | None,
    occurred_at: datetime,
) -> bool:
    if member.status != "active" or membership is None or membership.status != "active":
        return False
    return (
        _as_utc(membership.starts_at)
        <= occurred_at
        < _as_utc(membership.ends_at)
    )


def _latest_membership(session: Session, member_id: UUID) -> Membership | None:
    return session.exec(
        select(Membership)
        .where(Membership.member_id == member_id)
        .order_by(Membership.ends_at.desc())
    ).first()


def _record_attempt(
    session: Session,
    device_id: UUID,
    result: str,
    occurred_at: datetime,
) -> None:
    session.add(
        KioskAttempt(device_id=device_id, result=result, occurred_at=occurred_at)
    )
    session.commit()


def _access_code_hash(code: str) -> str:
    return hmac.new(signing_secret(), code.encode("utf-8"), sha256).hexdigest()


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)
