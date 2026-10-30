import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.inventory.models import CashSession
from app.modules.memberships.gateway import (
    ChargeOutcome,
    ChargeStatus,
    GatewayOutcomeUnknown,
    PaymentGateway,
    VerifiedWebhook,
)
from app.modules.memberships.models import (
    Member,
    MemberConsent,
    Membership,
    MembershipEvent,
    Payment,
    PaymentAttempt,
    PaymentAttemptEvent,
    PaymentMethod,
    Plan,
    ProviderWebhookEvent,
    utc_now,
)


class BillingError(Exception):
    pass


class MemberNotFound(BillingError):
    pass


class PlanUnavailable(BillingError):
    pass


class PlanNotFound(BillingError):
    pass


class ConsentRequired(BillingError):
    pass


class PaymentMethodUnavailable(BillingError):
    pass


class MembershipAlreadyExists(BillingError):
    pass


class IdempotencyConflict(BillingError):
    pass


class RetryNotAllowed(BillingError):
    pass


class WebhookConflict(BillingError):
    pass


class PaymentAttemptNotFound(BillingError):
    pass


class GatewayProviderMismatch(BillingError):
    pass


class InvalidMemberData(BillingError):
    pass


class DuplicateMemberEmail(BillingError):
    pass


class MembershipNotFound(BillingError):
    pass


class InvalidMembershipTransition(BillingError):
    pass


class CancellationReasonRequired(BillingError):
    pass


class CashSessionRequired(BillingError):
    pass


class MembershipPaymentNotAllowed(BillingError):
    pass


class InvalidMembershipPayment(BillingError):
    pass


PRIVACY_NOTICE_VERSION = "privacidad-v1"
NON_TERMINAL_MEMBERSHIP_STATUSES = ("pending_payment", "active", "frozen", "suspended")
MANUAL_MEMBERSHIP_PAYMENT_METHODS = ("cash", "card", "transfer")


@dataclass(frozen=True)
class MembershipChargeResult:
    membership_id: UUID
    payment_attempt_id: UUID
    status: str
    payment_id: UUID | None
    idempotent_replay: bool = False


@dataclass(frozen=True)
class MembershipPaymentResult:
    payment_id: UUID
    payment_attempt_id: UUID
    membership_id: UUID
    member_id: UUID
    plan_id: UUID
    plan_name: str
    amount_cents: int
    currency: str
    method: str
    paid_at: datetime
    cash_session_id: UUID
    period_starts_at: datetime
    period_ends_at: datetime
    membership_status: str
    auto_renew: bool
    renewed: bool
    idempotent_replay: bool = False


@dataclass(frozen=True)
class RegisteredMember:
    id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str
    consent_recorded: bool


@dataclass(frozen=True)
class MembershipState:
    membership_id: UUID
    member_id: UUID
    plan_id: UUID
    plan_name: str
    status: str
    starts_at: datetime
    ends_at: datetime
    auto_renew: bool
    previous_status: str | None = None
    plan_changed: bool = False


DEFAULT_MEMBER_PAGE_SIZE = 25
MAX_MEMBER_PAGE_SIZE = 100
MEMBER_EXPIRING_SOON_DAYS = 7
MEMBER_SORT_FIELDS = ("name", "plan", "renewal")
MEMBER_SORT_DIRECTIONS = ("asc", "desc")
MEMBER_STATE_FILTERS = ("active", "expiring_soon", "frozen", "pending")


@dataclass(frozen=True)
class MemberOverview:
    id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str
    membership_status: str | None
    plan_name: str | None
    membership_starts_at: datetime | None
    membership_ends_at: datetime | None
    auto_renew: bool | None


@dataclass(frozen=True)
class MemberDirectorySummary:
    total: int
    active: int
    expiring_soon: int
    frozen: int
    pending: int


@dataclass(frozen=True)
class MemberPlanOption:
    id: UUID
    name: str


@dataclass(frozen=True)
class MemberPage:
    items: list[MemberOverview]
    total: int
    page: int
    page_size: int
    pages: int
    summary: MemberDirectorySummary
    plans: list[MemberPlanOption]


def list_member_overview(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_MEMBER_PAGE_SIZE,
    search: str | None = None,
    sort: str = "name",
    direction: str = "asc",
    state: str | None = None,
    plan_id: UUID | None = None,
) -> MemberPage:
    """Return a page of members with their most recent membership and plan.

    The latest membership per member is ranked with a window function so that
    counting, filtering, sorting and pagination run in the database. ``sort``
    accepts ``name``, ``plan`` or ``renewal``; ``state`` filters by the same
    buckets exposed in the summary (``active``, ``expiring_soon``, ``frozen``,
    ``pending``) and ``plan_id`` narrows to members whose latest membership uses
    that plan. Summary counters and the ``plans`` options are club-wide and
    intentionally ignore the search term and filters so the header stays stable.
    """
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    if sort not in MEMBER_SORT_FIELDS:
        raise ValueError("Unsupported member sort field")
    if direction not in MEMBER_SORT_DIRECTIONS:
        raise ValueError("Unsupported member sort direction")
    if state is not None and state not in MEMBER_STATE_FILTERS:
        raise ValueError("Unsupported member state filter")
    page_size = min(page_size, MAX_MEMBER_PAGE_SIZE)
    term = (search or "").strip().lower()

    ranked = _latest_membership_subquery()
    membership_join = and_(ranked.c.member_id == Member.id, ranked.c.rn == 1)
    count_stmt = (
        select(func.count(Member.id))
        .select_from(Member)
        .outerjoin(ranked, membership_join)
        .outerjoin(Membership, Membership.id == ranked.c.membership_id)
        .outerjoin(Plan, Plan.id == Membership.plan_id)
    )
    rows_stmt = (
        select(Member, Membership, Plan)
        .outerjoin(ranked, membership_join)
        .outerjoin(Membership, Membership.id == ranked.c.membership_id)
        .outerjoin(Plan, Plan.id == Membership.plan_id)
    )
    conditions = []
    if term:
        conditions.append(_member_search_condition(term))
    if state is not None:
        conditions.append(_member_state_condition(state))
    if plan_id is not None:
        conditions.append(Membership.plan_id == plan_id)
    for condition in conditions:
        count_stmt = count_stmt.where(condition)
        rows_stmt = rows_stmt.where(condition)

    total = int(session.exec(count_stmt).one() or 0)
    rows = session.exec(
        rows_stmt.order_by(*_member_order_by(sort, direction))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        MemberOverview(
            id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            email=member.email,
            phone=member.phone,
            status=member.status,
            membership_status=membership.status if membership is not None else None,
            plan_name=plan.name if plan is not None else None,
            membership_starts_at=_as_utc(membership.starts_at) if membership is not None else None,
            membership_ends_at=_as_utc(membership.ends_at) if membership is not None else None,
            auto_renew=membership.auto_renew if membership is not None else None,
        )
        for member, membership, plan in rows
    ]
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return MemberPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=member_directory_summary(session),
        plans=_member_plan_options(session),
    )


def _member_plan_options(session: Session) -> list[MemberPlanOption]:
    """Distinct plans held by members' latest memberships, for the filter."""
    ranked = _latest_membership_subquery()
    membership_join = and_(ranked.c.member_id == Member.id, ranked.c.rn == 1)
    rows = session.exec(
        select(Plan.id, Plan.name)
        .select_from(Member)
        .outerjoin(ranked, membership_join)
        .outerjoin(Membership, Membership.id == ranked.c.membership_id)
        .outerjoin(Plan, Plan.id == Membership.plan_id)
        .where(Plan.id.is_not(None))
        .distinct()
        .order_by(Plan.name, Plan.id)
    ).all()
    return [MemberPlanOption(id=row[0], name=row[1]) for row in rows]


def _latest_membership_subquery():
    return (
        select(
            Membership.id.label("membership_id"),
            Membership.member_id.label("member_id"),
            func.row_number()
            .over(
                partition_by=Membership.member_id,
                order_by=(Membership.created_at.desc(), Membership.id.desc()),
            )
            .label("rn"),
        )
        .subquery()
    )


def _member_search_condition(term: str):
    # Each word has to match some field on its own, so writing the full name
    # ("Ana López") finds the member even though name and surname live in
    # separate columns.
    tokens = term.split() or [term]
    conditions = []
    for token in tokens:
        like = f"%{token}%"
        conditions.append(
            or_(
                func.lower(Member.first_name).like(like),
                func.lower(Member.last_name).like(like),
                func.lower(func.coalesce(Member.email, "")).like(like),
                func.lower(func.coalesce(Member.phone, "")).like(like),
                func.lower(func.coalesce(Plan.name, "")).like(like),
            )
        )
    return and_(*conditions)


def _member_state_condition(state: str):
    if state == "active":
        return Membership.status == "active"
    if state == "frozen":
        return Membership.status == "frozen"
    if state == "pending":
        return or_(Member.status == "pending", Membership.status == "pending_payment")
    moment = _as_utc(utc_now())
    soon = moment + timedelta(days=MEMBER_EXPIRING_SOON_DAYS)
    return and_(
        Membership.status == "active",
        Membership.ends_at >= moment,
        Membership.ends_at <= soon,
    )


def _member_order_by(sort: str, direction: str) -> list:
    descending = direction == "desc"
    if sort == "plan":
        order = [(Plan.name.desc() if descending else Plan.name.asc()).nulls_last()]
    elif sort == "renewal":
        order = [(Membership.ends_at.desc() if descending else Membership.ends_at.asc()).nulls_last()]
    else:
        order = [
            Member.last_name.desc() if descending else Member.last_name.asc(),
            Member.first_name.desc() if descending else Member.first_name.asc(),
        ]
    order.append(Member.id)
    return order


def member_directory_summary(session: Session, *, now: datetime | None = None) -> MemberDirectorySummary:
    moment = _as_utc(now or utc_now())
    soon = moment + timedelta(days=MEMBER_EXPIRING_SOON_DAYS)
    ranked = _latest_membership_subquery()
    membership_join = and_(ranked.c.member_id == Member.id, ranked.c.rn == 1)
    statement = (
        select(
            func.count(Member.id),
            func.coalesce(func.sum(case((Membership.status == "active", 1), else_=0)), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Membership.status == "active",
                                Membership.ends_at >= moment,
                                Membership.ends_at <= soon,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(func.sum(case((Membership.status == "frozen", 1), else_=0)), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            or_(Member.status == "pending", Membership.status == "pending_payment"),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(Member)
        .outerjoin(ranked, membership_join)
        .outerjoin(Membership, Membership.id == ranked.c.membership_id)
    )
    row = session.exec(statement).one()
    return MemberDirectorySummary(
        total=int(row[0] or 0),
        active=int(row[1] or 0),
        expiring_soon=int(row[2] or 0),
        frozen=int(row[3] or 0),
        pending=int(row[4] or 0),
    )


def register_member(
    session: Session,
    *,
    first_name: str,
    last_name: str,
    email: str | None = None,
    phone: str | None = None,
    privacy_notice_accepted: bool = False,
    document_version: str = PRIVACY_NOTICE_VERSION,
    now: datetime | None = None,
) -> RegisteredMember:
    """Register a new member (alta) with an optional privacy consent.

    The member starts as ``pending``: the plan, first charge and membership
    activation happen once the gateway can tokenize a payment method. Consent is
    recorded here when it was signed at the desk; payments still require an
    active consent before activating a membership.
    """
    first, last, normalized_email, normalized_phone = _normalize_member_fields(
        first_name, last_name, email, phone
    )
    occurred_at = _as_utc(now or utc_now())
    if normalized_email is not None and _member_email_taken(session, normalized_email):
        raise DuplicateMemberEmail("Ya existe un socio con ese correo")
    member = Member(
        first_name=first,
        last_name=last,
        email=normalized_email,
        phone=normalized_phone,
        status="pending",
    )
    session.add(member)
    if privacy_notice_accepted:
        session.add(
            MemberConsent(
                member_id=member.id,
                consent_type="privacy_notice",
                document_version=document_version,
                accepted_at=occurred_at,
            )
        )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateMemberEmail("Ya existe un socio con ese correo") from error
    return RegisteredMember(
        id=member.id,
        first_name=member.first_name,
        last_name=member.last_name,
        email=member.email,
        phone=member.phone,
        status=member.status,
        consent_recorded=privacy_notice_accepted,
    )


def update_member(
    session: Session,
    member_id: UUID,
    *,
    first_name: str,
    last_name: str,
    email: str | None = None,
    phone: str | None = None,
    now: datetime | None = None,
) -> Member:
    """Update a member's contact details, keeping the email unique."""
    member = session.get(Member, member_id)
    if member is None:
        raise MemberNotFound("El socio no existe")
    first, last, normalized_email, normalized_phone = _normalize_member_fields(
        first_name, last_name, email, phone
    )
    if normalized_email is not None and _member_email_taken(
        session, normalized_email, exclude_member_id=member_id
    ):
        raise DuplicateMemberEmail("Ya existe un socio con ese correo")
    member.first_name = first
    member.last_name = last
    member.email = normalized_email
    member.phone = normalized_phone
    member.updated_at = _as_utc(now or utc_now())
    session.add(member)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateMemberEmail("Ya existe un socio con ese correo") from error
    session.refresh(member)
    return member


def _non_terminal_membership(session: Session, member_id: UUID) -> Membership | None:
    return session.exec(
        select(Membership).where(
            Membership.member_id == member_id,
            Membership.status.in_(NON_TERMINAL_MEMBERSHIP_STATUSES),
        )
    ).first()


def _membership_state(
    session: Session,
    membership: Membership,
    *,
    previous_status: str | None = None,
    plan_changed: bool = False,
) -> MembershipState:
    plan = session.get(Plan, membership.plan_id)
    return MembershipState(
        membership_id=membership.id,
        member_id=membership.member_id,
        plan_id=membership.plan_id,
        plan_name=plan.name if plan is not None else "",
        status=membership.status,
        starts_at=_as_utc(membership.starts_at),
        ends_at=_as_utc(membership.ends_at),
        auto_renew=membership.auto_renew,
        previous_status=previous_status,
        plan_changed=plan_changed,
    )


def update_plan_daily_entry_limit(
    session: Session,
    plan_id: UUID,
    *,
    daily_entry_limit: int | None,
) -> Plan:
    """Set or clear the plan's per-club-day entry limit for the kiosk."""
    if daily_entry_limit is not None and daily_entry_limit < 1:
        raise ValueError("daily_entry_limit must be at least 1 or null")
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise PlanNotFound("Plan was not found")
    plan.daily_entry_limit = daily_entry_limit
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def assign_membership_plan(
    session: Session,
    *,
    member_id: UUID,
    plan_id: UUID,
    auto_renew: bool = False,
    starts_at: datetime | None = None,
    actor_id: UUID | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> MembershipState:
    """Assign or change a member's plan, activating the membership without charging.

    Deliberate first-version shortcut: no payment or attempt is recorded. The
    activation is auditable through a membership event carrying ``no_charge`` so
    the missing charge is explicit. Assigning or changing a plan starts a fresh
    period from today and leaves the membership ``active``.
    """
    moment = _as_utc(now or utc_now())
    start = _as_utc(starts_at) if starts_at is not None else moment
    member = session.get(Member, member_id)
    if member is None or member.status == "inactive":
        raise MemberNotFound("El socio no existe o está inactivo")
    plan = session.get(Plan, plan_id)
    if plan is None or not plan.is_active:
        raise PlanUnavailable("El plan no existe o no está activo")
    metadata: dict[str, str | bool] = {"plan_id": str(plan_id), "no_charge": True}
    if note:
        metadata["note"] = note

    membership = _non_terminal_membership(session, member_id)
    if membership is None:
        membership = Membership(
            member_id=member_id,
            plan_id=plan_id,
            status="active",
            starts_at=start,
            ends_at=start + timedelta(days=plan.duration_days),
            auto_renew=auto_renew,
        )
        session.add(membership)
        session.add(
            MembershipEvent(
                membership_id=membership.id,
                event_type="manual_activation",
                to_status="active",
                actor_type="employee" if actor_id is not None else "system",
                actor_id=actor_id,
                event_metadata=metadata,
            )
        )
        previous_status = None
        plan_changed = False
    else:
        previous_status = membership.status
        plan_changed = membership.plan_id != plan_id
        membership.plan_id = plan_id
        membership.starts_at = start
        membership.ends_at = start + timedelta(days=plan.duration_days)
        membership.auto_renew = auto_renew
        membership.status = "active"
        membership.updated_at = moment
        session.add(membership)
        session.add(
            MembershipEvent(
                membership_id=membership.id,
                event_type="plan_changed" if plan_changed else "manual_activation",
                from_status=previous_status,
                to_status="active",
                actor_type="employee" if actor_id is not None else "system",
                actor_id=actor_id,
                event_metadata=metadata,
            )
        )

    if member.status == "pending":
        member.status = "active"
        member.updated_at = moment
        session.add(member)

    session.commit()
    session.refresh(membership)
    return _membership_state(
        session, membership, previous_status=previous_status, plan_changed=plan_changed
    )


def _transition_membership(
    session: Session,
    member_id: UUID,
    *,
    to_status: str,
    event_type: str,
    allowed_from: tuple[str, ...],
    actor_id: UUID | None,
    metadata: dict[str, str | bool] | None = None,
    now: datetime | None = None,
) -> MembershipState:
    moment = _as_utc(now or utc_now())
    membership = _non_terminal_membership(session, member_id)
    if membership is None:
        raise MembershipNotFound("El socio no tiene una membresía vigente")
    if membership.status not in allowed_from:
        raise InvalidMembershipTransition(
            f"No se puede pasar la membresía de '{membership.status}' a '{to_status}'"
        )
    previous_status = membership.status
    membership.status = to_status
    membership.updated_at = moment
    session.add(membership)
    session.add(
        MembershipEvent(
            membership_id=membership.id,
            event_type=event_type,
            from_status=previous_status,
            to_status=to_status,
            actor_type="employee" if actor_id is not None else "system",
            actor_id=actor_id,
            event_metadata=metadata or {},
        )
    )
    session.commit()
    session.refresh(membership)
    return _membership_state(session, membership, previous_status=previous_status)


def freeze_membership(
    session: Session,
    member_id: UUID,
    *,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MembershipState:
    return _transition_membership(
        session,
        member_id,
        to_status="frozen",
        event_type="frozen",
        allowed_from=("active",),
        actor_id=actor_id,
        now=now,
    )


def resume_membership(
    session: Session,
    member_id: UUID,
    *,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MembershipState:
    return _transition_membership(
        session,
        member_id,
        to_status="active",
        event_type="resumed",
        allowed_from=("frozen",),
        actor_id=actor_id,
        now=now,
    )


def cancel_membership(
    session: Session,
    member_id: UUID,
    *,
    reason: str,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MembershipState:
    if not reason or not reason.strip():
        raise CancellationReasonRequired("La cancelación requiere un motivo")
    return _transition_membership(
        session,
        member_id,
        to_status="cancelled",
        event_type="cancelled",
        allowed_from=("pending_payment", "active", "frozen", "suspended"),
        actor_id=actor_id,
        metadata={"reason": reason.strip()},
        now=now,
    )


def collect_membership_payment(
    session: Session,
    *,
    member_id: UUID,
    plan_id: UUID | None,
    payment_method: str,
    idempotency_key: str,
    note: str | None = None,
    auto_renew: bool | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> MembershipPaymentResult:
    """Record a staff-collected membership payment and start or extend the period.

    This is the manual front-desk path (cash, card or transfer declared by the
    operator), not a gateway charge. It deliberately records a successful
    ``PaymentAttempt`` with no provider so the payment remains traceable and
    idempotent through the same tables as the card flow. Every payment requires
    an open cash session and is linked to it; only cash changes the expected
    drawer amount when the shift closes.
    """
    key = (idempotency_key or "").strip()
    if not key:
        raise InvalidMembershipPayment("La clave de idempotencia es obligatoria")
    if len(key) > 128:
        raise InvalidMembershipPayment("La clave de idempotencia es demasiado larga")
    if payment_method not in MANUAL_MEMBERSHIP_PAYMENT_METHODS:
        raise InvalidMembershipPayment("Forma de pago no válida para membresías")
    normalized_note = (note or "").strip() or None
    if normalized_note is not None and len(normalized_note) > 200:
        raise InvalidMembershipPayment("La nota no puede superar 200 caracteres")

    fingerprint = _fingerprint(
        {
            "operation": "manual_membership_payment",
            "member_id": str(member_id),
            "plan_id": str(plan_id) if plan_id is not None else None,
            "payment_method": payment_method,
            "note": normalized_note,
            "auto_renew": None if auto_renew is None else str(auto_renew),
        }
    )
    existing = session.exec(
        select(PaymentAttempt).where(PaymentAttempt.idempotency_key == key)
    ).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyConflict("La clave de idempotencia ya se usó para otro cobro")
        return _manual_payment_result(session, existing, idempotent_replay=True)

    moment = _as_utc(now or utc_now())
    member = session.get(Member, member_id)
    if member is None or member.status == "inactive":
        raise MemberNotFound("El socio no existe o está inactivo")

    cash_session = session.exec(
        select(CashSession)
        .where(CashSession.status == "open")
        .order_by(CashSession.opened_at.desc())
        .with_for_update()
    ).first()
    if cash_session is None:
        raise CashSessionRequired("Abre un turno de caja antes de registrar el cobro")

    membership = session.exec(
        select(Membership)
        .where(
            Membership.member_id == member_id,
            Membership.status.in_(NON_TERMINAL_MEMBERSHIP_STATUSES),
        )
        .with_for_update()
    ).first()
    if membership is not None and membership.status != "active":
        raise MembershipPaymentNotAllowed(
            f"No se puede cobrar una membresía en estado '{membership.status}'. "
            "Reanuda o cancela ese estado antes de registrar el cobro."
        )

    target_plan_id = plan_id if plan_id is not None else (membership.plan_id if membership is not None else None)
    if target_plan_id is None:
        raise InvalidMembershipPayment("Selecciona un plan para la membresía")
    plan = session.get(Plan, target_plan_id)
    if plan is None or plan.price_cents <= 0:
        raise PlanUnavailable("El plan no existe o no requiere cobro")
    if plan_id is not None and not plan.is_active:
        raise PlanUnavailable("El plan no está activo")

    previous_ends_at: datetime | None = None
    previous_plan_id: UUID | None = None
    previous_status: str | None = None
    if membership is None:
        period_start = moment
        period_end = moment + timedelta(days=plan.duration_days)
        membership = Membership(
            member_id=member_id,
            plan_id=plan.id,
            status="active",
            starts_at=period_start,
            ends_at=period_end,
            auto_renew=bool(auto_renew) if auto_renew is not None else False,
        )
        session.add(membership)
        session.flush()
        event_type = "payment_confirmed"
        event_from_status = None
        period_changed = False
    else:
        previous_status = membership.status
        previous_ends_at = _as_utc(membership.ends_at)
        previous_plan_id = membership.plan_id
        period_start = max(moment, previous_ends_at)
        period_end = period_start + timedelta(days=plan.duration_days)
        membership.plan_id = plan.id
        membership.status = "active"
        membership.ends_at = period_end
        membership.updated_at = moment
        if auto_renew is not None:
            membership.auto_renew = auto_renew
        session.add(membership)
        event_type = "renewed"
        event_from_status = previous_status
        period_changed = previous_plan_id != plan.id

    attempt_number = (
        session.exec(
            select(func.max(PaymentAttempt.attempt_number)).where(
                PaymentAttempt.membership_id == membership.id,
                PaymentAttempt.due_at == period_start,
            )
        ).one()
        or 0
    ) + 1
    attempt = PaymentAttempt(
        membership_id=membership.id,
        payment_method_id=None,
        method=payment_method,
        provider=None,
        provider_reference=None,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        attempt_number=attempt_number,
        amount_cents=plan.price_cents,
        currency=plan.currency,
        status="succeeded",
        due_at=period_start,
        resolved_at=moment,
    )
    session.add(attempt)
    session.flush()
    payment = Payment(
        payment_attempt_id=attempt.id,
        member_id=member_id,
        membership_id=membership.id,
        amount_cents=plan.price_cents,
        currency=plan.currency,
        method=payment_method,
        paid_at=moment,
        period_starts_at=period_start,
        period_ends_at=period_end,
        cash_session_id=cash_session.id,
        collected_by=actor_id,
        note=normalized_note,
    )
    session.add(payment)
    session.add(
        _attempt_event(
            attempt,
            None,
            "succeeded",
            "manual_payment_recorded",
            "operator",
        )
    )

    metadata: dict[str, object] = {
        "payment_id": str(payment.id),
        "payment_attempt_id": str(attempt.id),
        "payment_method": payment_method,
        "amount_cents": plan.price_cents,
        "currency": plan.currency,
        "cash_session_id": str(cash_session.id),
        "period_starts_at": period_start.isoformat(),
        "period_ends_at": period_end.isoformat(),
        "plan_id": str(plan.id),
    }
    if previous_ends_at is not None:
        metadata["previous_ends_at"] = previous_ends_at.isoformat()
    if previous_plan_id is not None and previous_plan_id != plan.id:
        metadata["previous_plan_id"] = str(previous_plan_id)
        metadata["plan_changed"] = True
    if normalized_note is not None:
        metadata["note"] = normalized_note
    session.add(
        MembershipEvent(
            membership_id=membership.id,
            event_type=event_type,
            from_status=event_from_status,
            to_status="active",
            actor_type="employee" if actor_id is not None else "system",
            actor_id=actor_id,
            event_metadata=metadata,
        )
    )
    if member.status == "pending":
        member.status = "active"
        member.updated_at = moment
        session.add(member)

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        existing = session.exec(
            select(PaymentAttempt).where(PaymentAttempt.idempotency_key == key)
        ).first()
        if existing is not None and existing.request_fingerprint == fingerprint:
            return _manual_payment_result(session, existing, idempotent_replay=True)
        raise MembershipPaymentNotAllowed(
            "No se pudo registrar el cobro porque otro intento similar ya existe"
        ) from error

    session.refresh(membership)
    session.refresh(payment)
    return MembershipPaymentResult(
        payment_id=payment.id,
        payment_attempt_id=attempt.id,
        membership_id=membership.id,
        member_id=member_id,
        plan_id=plan.id,
        plan_name=plan.name,
        amount_cents=payment.amount_cents,
        currency=payment.currency,
        method=payment.method,
        paid_at=_as_utc(payment.paid_at),
        cash_session_id=cash_session.id,
        period_starts_at=period_start,
        period_ends_at=period_end,
        membership_status=membership.status,
        auto_renew=membership.auto_renew,
        renewed=previous_ends_at is not None,
    )


def _manual_payment_result(
    session: Session,
    attempt: PaymentAttempt,
    *,
    idempotent_replay: bool,
) -> MembershipPaymentResult:
    membership = session.get(Membership, attempt.membership_id)
    payment = session.exec(
        select(Payment).where(Payment.payment_attempt_id == attempt.id)
    ).first()
    if membership is None or payment is None:
        raise BillingError("El cobro manual no tiene membresía o pago asociado")
    plan = session.get(Plan, membership.plan_id)
    if plan is None:
        raise PlanUnavailable("El plan del cobro ya no existe")
    period_start = _as_utc(payment.period_starts_at or attempt.due_at)
    period_end = _as_utc(payment.period_ends_at or membership.ends_at)
    membership_start = _as_utc(membership.starts_at)
    if payment.cash_session_id is None:
        raise BillingError("El cobro manual no tiene turno de caja asociado")
    return MembershipPaymentResult(
        payment_id=payment.id,
        payment_attempt_id=attempt.id,
        membership_id=membership.id,
        member_id=membership.member_id,
        plan_id=plan.id,
        plan_name=plan.name,
        amount_cents=payment.amount_cents,
        currency=payment.currency,
        method=payment.method,
        paid_at=_as_utc(payment.paid_at),
        cash_session_id=payment.cash_session_id,
        period_starts_at=period_start,
        period_ends_at=period_end,
        membership_status=membership.status,
        auto_renew=membership.auto_renew,
        renewed=period_start > membership_start,
        idempotent_replay=idempotent_replay,
    )


def start_first_charge(
    session: Session,
    gateway: PaymentGateway,
    *,
    member_id: UUID,
    plan_id: UUID,
    payment_method_id: UUID,
    idempotency_key: str,
    starts_at: datetime | None = None,
) -> MembershipChargeResult:
    if not idempotency_key.strip():
        raise ValueError("idempotency_key must not be empty")
    if starts_at is not None and (starts_at.tzinfo is None or starts_at.utcoffset() is None):
        raise ValueError("starts_at must be timezone-aware")
    request_fingerprint = _fingerprint(
        {
            "operation": "first_charge",
            "member_id": str(member_id),
            "plan_id": str(plan_id),
            "payment_method_id": str(payment_method_id),
            "starts_at": starts_at.isoformat() if starts_at is not None else None,
        }
    )

    existing = session.exec(
        select(PaymentAttempt).where(PaymentAttempt.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        _ensure_same_first_charge(
            session,
            existing,
            member_id,
            plan_id,
            payment_method_id,
            request_fingerprint,
        )
        return _result(session, existing, idempotent_replay=True)

    member = session.get(Member, member_id)
    if member is None or member.status == "inactive":
        raise MemberNotFound("Member is missing or inactive")

    consent = session.exec(
        select(MemberConsent).where(
            MemberConsent.member_id == member_id,
            MemberConsent.consent_type == "privacy_notice",
            MemberConsent.revoked_at.is_(None),
        )
    ).first()
    if consent is None:
        raise ConsentRequired("An active privacy notice consent is required")

    plan = session.get(Plan, plan_id)
    if plan is None or not plan.is_active or plan.price_cents <= 0:
        raise PlanUnavailable("Plan is missing, inactive, or does not require a charge")

    payment_method = _get_payment_method(session, payment_method_id, member_id)
    existing_membership = session.exec(
        select(Membership).where(
            Membership.member_id == member_id,
            Membership.status.in_(("pending_payment", "active", "frozen", "suspended")),
        )
    ).first()
    if existing_membership is not None:
        raise MembershipAlreadyExists("Member already has a non-terminal membership")

    start = starts_at or utc_now()
    membership = Membership(
        member_id=member_id,
        plan_id=plan_id,
        status="pending_payment",
        starts_at=start,
        ends_at=start + timedelta(days=plan.duration_days),
        auto_renew=True,
    )
    attempt = PaymentAttempt(
        membership_id=membership.id,
        payment_method_id=payment_method.id,
        method="card",
        provider=payment_method.provider,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        attempt_number=1,
        amount_cents=plan.price_cents,
        currency=plan.currency,
        status="pending",
        due_at=start,
    )
    session.add(membership)
    session.add(attempt)
    session.add(
        MembershipEvent(
            membership_id=membership.id,
            event_type="created_pending_payment",
            to_status="pending_payment",
            actor_type="system",
            event_metadata={},
        )
    )
    session.add(_attempt_event(attempt, None, "pending", "created", "api"))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.exec(
            select(PaymentAttempt).where(PaymentAttempt.idempotency_key == idempotency_key)
        ).first()
        if existing is None:
            raise
        _ensure_same_first_charge(
            session,
            existing,
            member_id,
            plan_id,
            payment_method_id,
            request_fingerprint,
        )
        return _result(session, existing, idempotent_replay=True)

    return _execute_attempt(session, gateway, attempt.id)


def retry_failed_charge(
    session: Session,
    gateway: PaymentGateway,
    *,
    failed_attempt_id: UUID,
    idempotency_key: str,
) -> MembershipChargeResult:
    if not idempotency_key.strip():
        raise ValueError("idempotency_key must not be empty")

    previous = session.get(PaymentAttempt, failed_attempt_id)
    if previous is None:
        raise PaymentAttemptNotFound("Payment attempt was not found")
    request_fingerprint = _fingerprint(
        {"operation": "retry", "failed_attempt_id": str(failed_attempt_id)}
    )

    existing = session.exec(
        select(PaymentAttempt).where(PaymentAttempt.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        if existing.request_fingerprint != request_fingerprint:
            raise IdempotencyConflict("Idempotency key was already used for a different charge")
        return _result(session, existing, idempotent_replay=True)

    membership = session.get(Membership, previous.membership_id)
    if previous.status != "failed" or membership is None or membership.status != "pending_payment":
        raise RetryNotAllowed("Only a definitively failed first charge can be retried")
    if session.exec(select(Payment).where(Payment.membership_id == membership.id)).first() is not None:
        raise RetryNotAllowed("Membership already has a confirmed payment")
    if idempotency_key == previous.idempotency_key:
        raise IdempotencyConflict("A retry requires a new idempotency key")

    last_attempt_number = session.exec(
        select(func.max(PaymentAttempt.attempt_number)).where(
            PaymentAttempt.membership_id == previous.membership_id,
            PaymentAttempt.due_at == previous.due_at,
        )
    ).one()
    attempt = PaymentAttempt(
        membership_id=previous.membership_id,
        payment_method_id=previous.payment_method_id,
        method=previous.method,
        provider=previous.provider,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        attempt_number=(last_attempt_number or 0) + 1,
        amount_cents=previous.amount_cents,
        currency=previous.currency,
        status="pending",
        due_at=previous.due_at,
    )
    session.add(attempt)
    session.add(_attempt_event(attempt, None, "pending", "retry_created", "worker"))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.exec(
            select(PaymentAttempt).where(PaymentAttempt.idempotency_key == idempotency_key)
        ).first()
        if existing is None:
            raise
        if existing.request_fingerprint != request_fingerprint:
            raise IdempotencyConflict("Idempotency key was already used for a different charge")
        return _result(session, existing, idempotent_replay=True)

    return _execute_attempt(session, gateway, attempt.id)


def process_verified_webhook(
    session: Session,
    webhook: VerifiedWebhook,
) -> MembershipChargeResult:
    event = session.exec(
        select(ProviderWebhookEvent)
        .where(
            ProviderWebhookEvent.provider == webhook.provider,
            ProviderWebhookEvent.provider_event_id == webhook.provider_event_id,
        )
        .with_for_update()
    ).first()
    if event is not None:
        if event.payload_sha256 != webhook.payload_sha256:
            raise WebhookConflict("Webhook event ID was reused with a different payload")
        if event.status == "processed":
            attempt = session.get(PaymentAttempt, event.payment_attempt_id)
            if attempt is None:
                raise PaymentAttemptNotFound("Webhook payment attempt was not found")
            return _result(session, attempt, idempotent_replay=True)

    attempt = session.get(PaymentAttempt, webhook.payment_attempt_id)
    if attempt is None:
        raise PaymentAttemptNotFound("Webhook payment attempt was not found")
    if attempt.provider != webhook.provider:
        raise GatewayProviderMismatch("Webhook provider does not match payment attempt")

    if event is None:
        event = ProviderWebhookEvent(
            provider=webhook.provider,
            provider_event_id=webhook.provider_event_id,
            event_type=webhook.event_type,
            payload_sha256=webhook.payload_sha256,
            payment_attempt_id=attempt.id,
            status="received",
        )
        session.add(event)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            duplicate = session.exec(
                select(ProviderWebhookEvent).where(
                    ProviderWebhookEvent.provider == webhook.provider,
                    ProviderWebhookEvent.provider_event_id == webhook.provider_event_id,
                )
            ).first()
            if duplicate is None or duplicate.status != "processed":
                raise
            duplicate_attempt = session.get(PaymentAttempt, duplicate.payment_attempt_id)
            if duplicate_attempt is None:
                raise PaymentAttemptNotFound("Webhook payment attempt was not found")
            return _result(session, duplicate_attempt, idempotent_replay=True)
    else:
        event.payment_attempt_id = attempt.id

    result = _apply_outcome(
        session,
        attempt,
        webhook.outcome,
        source="webhook",
        webhook_event_id=event.id,
        commit=False,
    )
    event.status = "processed"
    event.processed_at = utc_now()
    session.commit()
    return result


def _execute_attempt(
    session: Session,
    gateway: PaymentGateway,
    payment_attempt_id: UUID,
) -> MembershipChargeResult:
    attempt = session.get(PaymentAttempt, payment_attempt_id)
    if attempt is None:
        raise PaymentAttemptNotFound("Payment attempt was not found")
    if attempt.status in {"succeeded", "failed", "cancelled"}:
        return _result(session, attempt, idempotent_replay=True)

    payment_method = session.get(PaymentMethod, attempt.payment_method_id)
    if payment_method is None or payment_method.status != "active":
        raise PaymentMethodUnavailable("Saved payment method is missing or inactive")

    previous_status = attempt.status
    if attempt.status != "processing":
        attempt.status = "processing"
        session.add(_attempt_event(attempt, previous_status, "processing", "charge_submitted", "api"))
        session.commit()
        session.refresh(attempt)

    try:
        outcome = gateway.charge(attempt, payment_method)
    except GatewayOutcomeUnknown as error:
        outcome = ChargeOutcome(status=ChargeStatus.UNKNOWN, failure_code=error.failure_code)

    return _apply_outcome(session, attempt, outcome, source="api", commit=True)


def _apply_outcome(
    session: Session,
    attempt: PaymentAttempt,
    outcome: ChargeOutcome,
    *,
    source: str,
    webhook_event_id: UUID | None = None,
    commit: bool,
) -> MembershipChargeResult:
    attempt = session.exec(
        select(PaymentAttempt).where(PaymentAttempt.id == attempt.id).with_for_update()
    ).one()
    if attempt.status == "succeeded":
        if commit:
            session.rollback()
        return _result(session, attempt, idempotent_replay=True)

    previous_status = attempt.status
    next_status = outcome.status.value
    attempt.status = next_status
    attempt.provider_reference = outcome.provider_reference or attempt.provider_reference
    attempt.failure_code = outcome.failure_code
    attempt.resolved_at = (
        outcome.occurred_at or utc_now()
        if next_status in {"succeeded", "failed", "cancelled"}
        else None
    )
    if previous_status != next_status:
        session.add(
            _attempt_event(
                attempt,
                previous_status,
                next_status,
                f"charge_{next_status}",
                source,
                webhook_event_id,
            )
        )

    if next_status == "succeeded":
        payment = session.exec(
            select(Payment).where(Payment.payment_attempt_id == attempt.id)
        ).first()
        membership = session.get(Membership, attempt.membership_id)
        if membership is None:
            raise BillingError("Membership for payment attempt no longer exists")
        if payment is None:
            payment = Payment(
                payment_attempt_id=attempt.id,
                member_id=membership.member_id,
                membership_id=membership.id,
                amount_cents=attempt.amount_cents,
                currency=attempt.currency,
                method=attempt.method,
                paid_at=outcome.occurred_at or utc_now(),
                period_starts_at=membership.starts_at,
                period_ends_at=membership.ends_at,
            )
            session.add(payment)
        if membership.status == "pending_payment":
            membership.status = "active"
            membership.updated_at = utc_now()
            session.add(
                MembershipEvent(
                    membership_id=membership.id,
                    event_type="payment_confirmed",
                    from_status="pending_payment",
                    to_status="active",
                    actor_type="provider" if source == "webhook" else "system",
                    event_metadata={},
                )
            )
        member = session.get(Member, membership.member_id)
        if member is not None and member.status == "pending":
            member.status = "active"
            member.updated_at = utc_now()

    if commit:
        session.commit()
    return _result(session, attempt)


def _attempt_event(
    attempt: PaymentAttempt,
    from_status: str | None,
    to_status: str,
    event_type: str,
    source: str,
    webhook_event_id: UUID | None = None,
) -> PaymentAttemptEvent:
    return PaymentAttemptEvent(
        payment_attempt_id=attempt.id,
        webhook_event_id=webhook_event_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        source=source,
    )


def _get_payment_method(session: Session, payment_method_id: UUID, member_id: UUID) -> PaymentMethod:
    payment_method = session.get(PaymentMethod, payment_method_id)
    if (
        payment_method is None
        or payment_method.member_id != member_id
        or payment_method.status != "active"
    ):
        raise PaymentMethodUnavailable("Saved payment method is missing, inactive, or belongs to another member")
    return payment_method


def _ensure_same_first_charge(
    session: Session,
    attempt: PaymentAttempt,
    member_id: UUID,
    plan_id: UUID,
    payment_method_id: UUID,
    request_fingerprint: str,
) -> None:
    membership = session.get(Membership, attempt.membership_id)
    if (
        membership is None
        or membership.member_id != member_id
        or membership.plan_id != plan_id
        or attempt.payment_method_id != payment_method_id
        or attempt.request_fingerprint != request_fingerprint
    ):
        raise IdempotencyConflict("Idempotency key was already used for a different request")


def _fingerprint(values: dict[str, str | None]) -> str:
    serialized = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _member_email_taken(session: Session, email: str, *, exclude_member_id: UUID | None = None) -> bool:
    statement = select(Member.id).where(func.lower(Member.email) == email.lower())
    if exclude_member_id is not None:
        statement = statement.where(Member.id != exclude_member_id)
    return session.exec(statement).first() is not None


def _normalize_member_fields(
    first_name: str,
    last_name: str,
    email: str | None,
    phone: str | None,
) -> tuple[str, str, str | None, str | None]:
    first = first_name.strip()
    last = last_name.strip()
    if not first or not last:
        raise InvalidMemberData("El nombre y los apellidos son obligatorios")
    normalized_email = (email or "").strip() or None
    normalized_phone = (phone or "").strip() or None
    if normalized_email is None and normalized_phone is None:
        raise InvalidMemberData("Se requiere un correo o un teléfono de contacto")
    return first, last, normalized_email, normalized_phone


def _result(
    session: Session,
    attempt: PaymentAttempt,
    *,
    idempotent_replay: bool = False,
) -> MembershipChargeResult:
    payment = session.exec(
        select(Payment).where(Payment.payment_attempt_id == attempt.id)
    ).first()
    return MembershipChargeResult(
        membership_id=attempt.membership_id,
        payment_attempt_id=attempt.id,
        status=attempt.status,
        payment_id=payment.id if payment is not None else None,
        idempotent_replay=idempotent_replay,
    )