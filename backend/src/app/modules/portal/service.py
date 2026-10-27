"""Member self-service authentication.

Members sign in with a six-digit one-time code sent to the email registered by
the club. There is no member password, the code is stored only as an HMAC
digest, and the resulting session is an opaque token whose SHA-256 hash is the
only value kept in the database. Staff sessions use a separate table and
dependency, so a member token can never reach an administrative route.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import math
import os
import secrets
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlmodel import Session, select

from app.mailer import MailerError, send_email, preview_mode
from app.modules.inventory.service import member_account_balance
from app.modules.memberships.models import Member, Membership, Plan, utc_now
from app.modules.portal.models import (
    MemberAuthEvent,
    MemberLoginCode,
    MemberSession,
)

CODE_LIFETIME = timedelta(minutes=10)
CODE_MAX_ATTEMPTS = 5
CODE_REQUEST_WINDOW = timedelta(minutes=15)
CODE_MAX_REQUESTS = 5
MEMBER_SESSION_LIFETIME = timedelta(days=30)
LAST_SEEN_REFRESH = timedelta(minutes=5)
ACTIVE_MEMBER_STATUSES = ("active", "pending")


class MemberPortalError(Exception):
    pass


class MemberAuthUnavailable(MemberPortalError):
    pass


class InvalidMemberCode(MemberPortalError):
    pass


class InvalidMemberSession(MemberPortalError):
    pass


class MemberDeliveryFailed(MemberPortalError):
    pass


@dataclass(frozen=True)
class RequestCodeResult:
    expires_in: int
    preview_code: str | None


@dataclass(frozen=True)
class AuthenticatedMember:
    member_id: UUID
    session_id: UUID
    email: str
    first_name: str
    last_name: str
    status: str


@dataclass(frozen=True)
class MemberLoginResult:
    access_token: str
    token_type: str
    expires_at: datetime
    member: AuthenticatedMember


@dataclass(frozen=True)
class MemberMembershipSummary:
    plan_name: str
    status: str
    starts_at: datetime
    ends_at: datetime
    auto_renew: bool
    days_remaining: int


@dataclass(frozen=True)
class MemberProfile:
    id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str
    member_since: datetime
    membership: MemberMembershipSummary | None
    balance_cents: int
    access_enabled: bool


def request_login_code(
    session: Session,
    *,
    email: str,
    now: datetime | None = None,
) -> RequestCodeResult:
    """Send a code to a registered member.

    Unknown or inactive emails get the same successful result without an email
    so the endpoint cannot be used to discover members. Repeated requests inside
    the window are silently dropped for the same reason.
    """
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    normalized = _normalize_email(email)
    member = session.exec(select(Member).where(func.lower(Member.email) == normalized)).first()
    if member is None or member.status not in ACTIVE_MEMBER_STATUSES or not member.email:
        return RequestCodeResult(expires_in=_seconds(CODE_LIFETIME), preview_code=None)

    window_start = occurred_at - CODE_REQUEST_WINDOW
    recent_requests = session.exec(
        select(func.count(MemberLoginCode.id)).where(
            MemberLoginCode.member_id == member.id,
            MemberLoginCode.created_at >= window_start,
        )
    ).one()
    if int(recent_requests or 0) >= CODE_MAX_REQUESTS:
        session.add(
            MemberAuthEvent(
                member_id=member.id,
                event_type="code_requested",
                result="failure",
                reason_code="rate_limited",
                occurred_at=occurred_at,
            )
        )
        session.commit()
        return RequestCodeResult(expires_in=_seconds(CODE_LIFETIME), preview_code=None)

    code = f"{secrets.randbelow(1_000_000):06d}"
    login_code = MemberLoginCode(
        id=uuid4(),
        member_id=member.id,
        code_hash="",
        created_at=occurred_at,
        expires_at=occurred_at + CODE_LIFETIME,
    )
    login_code.code_hash = _code_hash(code, login_code.id, member.id)
    session.add(login_code)
    session.add(
        MemberAuthEvent(
            member_id=member.id,
            event_type="code_requested",
            result="success",
            occurred_at=occurred_at,
        )
    )
    session.commit()

    try:
        delivery = send_email(
            recipient=member.email,
            subject=f"Tu código de acceso a {_gym_name()}",
            body=(
                f"Tu código de acceso es {code}.\n\n"
                f"Vence en {CODE_LIFETIME.seconds // 60} minutos y solo puede usarse una vez. "
                "Si no lo solicitaste, ignora este mensaje."
            ),
            not_configured_message="El envío de códigos por correo no está configurado (SMTP_HOST).",
            failure_label="No se pudo enviar el código de acceso",
        )
    except MailerError as error:
        session.add(
            MemberAuthEvent(
                member_id=member.id,
                event_type="code_delivery",
                result="failure",
                reason_code="delivery_failed",
                occurred_at=occurred_at,
            )
        )
        session.commit()
        raise MemberDeliveryFailed(str(error)) from error

    session.add(
        MemberAuthEvent(
            member_id=member.id,
            event_type="code_delivery",
            result="success",
            reason_code=delivery,
            occurred_at=occurred_at,
        )
    )
    session.commit()
    return RequestCodeResult(
        expires_in=_seconds(CODE_LIFETIME),
        preview_code=code if preview_mode() else None,
    )


def verify_login_code(
    session: Session,
    *,
    email: str,
    code: str,
    now: datetime | None = None,
) -> MemberLoginResult:
    """Exchange a valid one-time code for a member session."""
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    normalized = _normalize_email(email)
    member = session.exec(select(Member).where(func.lower(Member.email) == normalized)).first()
    if member is None or member.status not in ACTIVE_MEMBER_STATUSES or not member.email:
        _record_code_failure(session, None, "invalid_code", occurred_at)
        raise InvalidMemberCode("Código inválido o expirado")

    login_code = session.exec(
        select(MemberLoginCode)
        .where(MemberLoginCode.member_id == member.id)
        .order_by(MemberLoginCode.created_at.desc())
    ).first()
    if (
        login_code is None
        or login_code.consumed_at is not None
        or login_code.attempts >= CODE_MAX_ATTEMPTS
        or _as_utc(login_code.expires_at) <= occurred_at
    ):
        _record_code_failure(session, member.id, "invalid_code", occurred_at)
        raise InvalidMemberCode("Código inválido o expirado")

    if not hmac.compare_digest(login_code.code_hash, _code_hash(code, login_code.id, member.id)):
        login_code.attempts += 1
        _record_code_failure(session, member.id, "invalid_code", occurred_at)
        raise InvalidMemberCode("Código inválido o expirado")

    login_code.consumed_at = occurred_at
    raw_token = secrets.token_urlsafe(32)
    expires_at = occurred_at + MEMBER_SESSION_LIFETIME
    member_session = MemberSession(
        member_id=member.id,
        token_sha256=_token_hash(raw_token),
        created_at=occurred_at,
        expires_at=expires_at,
        last_seen_at=occurred_at,
    )
    session.add(member_session)
    session.add(
        MemberAuthEvent(
            member_id=member.id,
            event_type="login",
            result="success",
            occurred_at=occurred_at,
        )
    )
    session.commit()
    session.refresh(member_session)
    return MemberLoginResult(
        access_token=raw_token,
        token_type="Bearer",
        expires_at=expires_at,
        member=_build_member(member, member_session),
    )


def authenticate_member_session(
    session: Session,
    access_token: str,
    *,
    now: datetime | None = None,
) -> AuthenticatedMember:
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    member_session = session.exec(
        select(MemberSession).where(MemberSession.token_sha256 == _token_hash(access_token))
    ).first()
    if (
        member_session is None
        or member_session.revoked_at is not None
        or _as_utc(member_session.expires_at) <= occurred_at
    ):
        raise InvalidMemberSession("Session is invalid or expired")
    member = session.get(Member, member_session.member_id)
    if member is None or member.status not in ACTIVE_MEMBER_STATUSES:
        raise InvalidMemberSession("Session is invalid or expired")
    if (
        member_session.last_seen_at is None
        or _as_utc(member_session.last_seen_at) <= occurred_at - LAST_SEEN_REFRESH
    ):
        member_session.last_seen_at = occurred_at
        session.add(member_session)
        session.commit()
    return _build_member(member, member_session)


def revoke_member_session(
    session: Session,
    member: AuthenticatedMember,
    *,
    now: datetime | None = None,
) -> None:
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    member_session = session.get(MemberSession, member.session_id)
    if member_session is None or member_session.member_id != member.member_id:
        raise InvalidMemberSession("Session is invalid or expired")
    if member_session.revoked_at is None:
        member_session.revoked_at = occurred_at
        session.add(
            MemberAuthEvent(
                member_id=member.member_id,
                event_type="logout",
                result="success",
                occurred_at=occurred_at,
            )
        )
        session.commit()


def member_profile(
    session: Session,
    member_id: UUID,
    *,
    now: datetime | None = None,
) -> MemberProfile:
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    member = session.get(Member, member_id)
    if member is None:
        raise MemberPortalError("Socio no encontrado")
    row = session.exec(
        select(Membership, Plan)
        .join(Plan, Plan.id == Membership.plan_id)
        .where(Membership.member_id == member_id)
        .order_by(Membership.ends_at.desc())
    ).first()
    membership: MemberMembershipSummary | None = None
    access_enabled = False
    if row is not None:
        current, plan = row
        starts_at = _as_utc(current.starts_at)
        ends_at = _as_utc(current.ends_at)
        access_enabled = (
            member.status == "active"
            and current.status == "active"
            and starts_at <= occurred_at < ends_at
        )
        membership = MemberMembershipSummary(
            plan_name=plan.name,
            status=current.status,
            starts_at=starts_at,
            ends_at=ends_at,
            auto_renew=current.auto_renew,
            days_remaining=max(0, math.ceil((ends_at - occurred_at).total_seconds() / 86400)),
        )
    return MemberProfile(
        id=member.id,
        first_name=member.first_name,
        last_name=member.last_name,
        email=member.email,
        phone=member.phone,
        status=member.status,
        member_since=_as_utc(member.created_at),
        membership=membership,
        balance_cents=member_account_balance(session, member.id),
        access_enabled=access_enabled,
    )


def _record_code_failure(
    session: Session,
    member_id: UUID | None,
    reason_code: str,
    occurred_at: datetime,
) -> None:
    session.add(
        MemberAuthEvent(
            member_id=member_id,
            event_type="code_verified",
            result="failure",
            reason_code=reason_code,
            occurred_at=occurred_at,
        )
    )
    session.commit()


def _build_member(member: Member, member_session: MemberSession) -> AuthenticatedMember:
    return AuthenticatedMember(
        member_id=member.id,
        session_id=member_session.id,
        email=member.email or "",
        first_name=member.first_name,
        last_name=member.last_name,
        status=member.status,
    )


def _code_hash(code: str, code_id: UUID, member_id: UUID) -> str:
    message = f"{code_id}:{member_id}:{code}".encode("utf-8")
    return hmac.new(_signing_secret(), message, sha256).hexdigest()


def _signing_secret() -> bytes:
    configured = os.getenv("SECRET_KEY", "").strip()
    if configured and configured not in {"change-me", "replace-me"}:
        return configured.encode("utf-8")
    if preview_mode():
        return b"preview-member-auth-only"
    raise MemberAuthUnavailable(
        "SECRET_KEY no está configurado; no se pueden emitir códigos de acceso."
    )


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("A valid email address is required")
    return normalized


def _gym_name() -> str:
    return os.getenv("GYM_NAME", "").strip() or "Centro Fit"


def _seconds(value: timedelta) -> int:
    return int(value.total_seconds())


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Authentication timestamps must be timezone-aware")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
