from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.access.models import (
    AccessDecision,
    AccessDirection,
    AccessEvent,
    AccessMemberNotFound,
    AccessReason,
    AccessRequest,
    AccessSnapshot,
    AccessWindow,
    utc_now,
)
from app.modules.memberships.models import Member, Membership, Plan
from app.timezone import DEFAULT_TIMEZONE, club_timezone

DEFAULT_ACCESS_PAGE_SIZE = 25
MAX_ACCESS_PAGE_SIZE = 100
ACCESS_STATES = ("authorized", "denied", "manual")


def evaluate_access(
    snapshot: AccessSnapshot | None,
    request: AccessRequest,
    *,
    timezone_name: str,
    last_successful_entry_at: datetime | None = None,
) -> AccessDecision:
    _require_aware(request.occurred_at)
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown gym timezone: {timezone_name}") from error

    if request.direction == AccessDirection.EXIT:
        return _decision(request, True, AccessReason.EXIT_ALLOWED)

    if snapshot is None or snapshot.member_id != request.member_id:
        return _decision(request, False, AccessReason.SNAPSHOT_MISSING)

    _require_aware(snapshot.membership_starts_at)
    _require_aware(snapshot.membership_ends_at)
    _require_aware(snapshot.cached_at)
    _require_aware(snapshot.valid_until)

    if request.occurred_at >= snapshot.valid_until:
        return _decision(request, False, AccessReason.SNAPSHOT_EXPIRED)
    if snapshot.membership_status != "active":
        return _decision(request, False, AccessReason.MEMBERSHIP_NOT_ACTIVE)
    if request.occurred_at < snapshot.membership_starts_at:
        return _decision(request, False, AccessReason.MEMBERSHIP_NOT_STARTED)
    if request.occurred_at >= snapshot.membership_ends_at:
        return _decision(request, False, AccessReason.MEMBERSHIP_EXPIRED)
    if snapshot.blocking_debt:
        return _decision(request, False, AccessReason.BLOCKING_DEBT)

    local_time = request.occurred_at.astimezone(local_timezone)
    if snapshot.allowed_windows is not None and not _is_within_schedule(local_time.weekday(), local_time.time(), snapshot.allowed_windows):
        return _decision(request, False, AccessReason.OUTSIDE_ALLOWED_HOURS)

    if snapshot.daily_entry_limit is not None and snapshot.entries_today >= snapshot.daily_entry_limit:
        return _decision(request, False, AccessReason.DAILY_LIMIT)

    if (
        last_successful_entry_at is not None
        and snapshot.antipassback_seconds > 0
        and 0 <= (request.occurred_at - last_successful_entry_at).total_seconds() < snapshot.antipassback_seconds
    ):
        return _decision(request, False, AccessReason.ANTIPASSBACK)

    if request.max_occupancy <= 0 or request.current_occupancy >= request.max_occupancy:
        return _decision(request, False, AccessReason.OCCUPANCY_FULL)

    return _decision(request, True, AccessReason.ENTRY_ALLOWED)


def _is_within_schedule(
    weekday: int,
    local_time: time,
    windows: tuple[AccessWindow, ...],
) -> bool:
    for window in windows:
        if not 0 <= window.weekday <= 6:
            continue
        if window.starts_at <= window.ends_at:
            if weekday == window.weekday and window.starts_at <= local_time < window.ends_at:
                return True
        elif (
            weekday == window.weekday and local_time >= window.starts_at
        ) or (
            weekday == (window.weekday + 1) % 7 and local_time < window.ends_at
        ):
            return True
    return False


def _decision(request: AccessRequest, authorized: bool, reason: AccessReason) -> AccessDecision:
    return AccessDecision(
        event_id=request.event_id,
        member_id=request.member_id,
        authorized=authorized,
        reason=reason,
        direction=request.direction,
        occurred_at=request.occurred_at,
        offline=request.offline,
    )


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Access timestamps must be timezone-aware")


@dataclass(frozen=True)
class AccessEventItem:
    id: UUID
    event_id: UUID
    member_id: UUID | None
    member_name: str | None
    member_email: str | None
    plan_name: str | None
    reader_id: str
    direction: str
    authorized: bool
    reason: str
    note: str | None
    source: str
    occurred_at: datetime
    offline: bool


@dataclass(frozen=True)
class AccessEventSummary:
    total: int
    authorized: int
    denied: int
    manual: int


@dataclass(frozen=True)
class AccessEventPage:
    items: list[AccessEventItem]
    total: int
    page: int
    page_size: int
    pages: int
    summary: AccessEventSummary


@dataclass(frozen=True)
class AccessTodaySummary:
    entries: int
    denied: int


def record_access_event(
    session: Session,
    decision: AccessDecision,
    *,
    reader_id: str,
    source: str = "reader",
    note: str | None = None,
) -> AccessEvent:
    """Persist an access decision, idempotent on the device ``event_id``.

    Members that are not in the database (for example a denial for an unknown
    card) are stored with a null ``member_id`` so the foreign key stays valid.
    """
    if source not in {"reader", "manual"}:
        raise ValueError("Unsupported access source")
    _require_aware(decision.occurred_at)

    existing = session.exec(select(AccessEvent).where(AccessEvent.event_id == decision.event_id)).first()
    if existing is not None:
        return existing

    member_id: UUID | None = decision.member_id
    if member_id is not None and session.get(Member, member_id) is None:
        member_id = None

    record = AccessEvent(
        event_id=decision.event_id,
        member_id=member_id,
        reader_id=reader_id,
        direction=decision.direction.value,
        authorized=decision.authorized,
        reason=decision.reason.value,
        note=note,
        source=source,
        occurred_at=decision.occurred_at,
        offline=decision.offline,
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.exec(select(AccessEvent).where(AccessEvent.event_id == decision.event_id)).first()
        if existing is None:
            raise
        return existing
    session.refresh(record)
    return record


def record_manual_access(
    session: Session,
    *,
    member_id: UUID,
    note: str | None = None,
    reader_id: str = "Recepción",
    occurred_at: datetime | None = None,
) -> AccessEvent:
    """Persist a reception-authorized entry that bypasses the reader.

    Manual overrides are always authorized entries with ``source="manual"`` so
    the bitácora keeps who was let in and why. Unlike reader decisions the
    member must exist, otherwise there is nobody to authorize.
    """
    if session.get(Member, member_id) is None:
        raise AccessMemberNotFound("Member was not found")
    decision = AccessDecision(
        event_id=uuid4(),
        member_id=member_id,
        authorized=True,
        reason=AccessReason.MANUAL_OVERRIDE,
        direction=AccessDirection.ENTRY,
        occurred_at=_as_utc(occurred_at or utc_now()),
        offline=False,
    )
    return record_access_event(
        session,
        decision,
        reader_id=reader_id,
        source="manual",
        note=(note or "").strip() or None,
    )


def list_access_events(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_ACCESS_PAGE_SIZE,
    search: str | None = None,
    state: str | None = None,
) -> AccessEventPage:
    """Return a page of access events enriched with member and plan data."""
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    if state is not None and state not in ACCESS_STATES:
        raise ValueError("Unsupported access state filter")
    page_size = min(page_size, MAX_ACCESS_PAGE_SIZE)
    term = (search or "").strip().lower()

    latest_plan_name = (
        select(Plan.name)
        .join(Membership, Membership.plan_id == Plan.id)
        .where(Membership.member_id == AccessEvent.member_id)
        .order_by(Membership.created_at.desc(), Membership.id.desc())
        .limit(1)
        .correlate(AccessEvent)
        .scalar_subquery()
    )

    def _apply_filters(statement):
        if term:
            like = f"%{term}%"
            statement = statement.where(
                or_(
                    func.lower(func.coalesce(Member.first_name, "")).like(like),
                    func.lower(func.coalesce(Member.last_name, "")).like(like),
                    func.lower(func.coalesce(Member.email, "")).like(like),
                    func.lower(AccessEvent.reader_id).like(like),
                )
            )
        if state == "manual":
            statement = statement.where(AccessEvent.source == "manual")
        elif state == "authorized":
            statement = statement.where(AccessEvent.source != "manual", AccessEvent.authorized.is_(True))
        elif state == "denied":
            statement = statement.where(AccessEvent.authorized.is_(False))
        return statement

    count_stmt = _apply_filters(
        select(func.count(AccessEvent.id)).select_from(AccessEvent).outerjoin(Member, Member.id == AccessEvent.member_id)
    )
    rows_stmt = _apply_filters(
        select(AccessEvent, Member, latest_plan_name.label("plan_name"))
        .select_from(AccessEvent)
        .outerjoin(Member, Member.id == AccessEvent.member_id)
    )

    total = int(session.exec(count_stmt).one() or 0)
    rows = session.exec(
        rows_stmt.order_by(AccessEvent.occurred_at.desc(), AccessEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [_build_access_event_item(event, member, plan_name) for event, member, plan_name in rows]

    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return AccessEventPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        summary=_access_event_summary(session),
    )


def _build_access_event_item(
    event: AccessEvent,
    member: Member | None,
    plan_name: str | None,
) -> AccessEventItem:
    member_name = f"{member.first_name} {member.last_name}".strip() if member is not None else None
    return AccessEventItem(
        id=event.id,
        event_id=event.event_id,
        member_id=event.member_id,
        member_name=member_name or None,
        member_email=member.email if member is not None else None,
        plan_name=plan_name,
        reader_id=event.reader_id,
        direction=event.direction,
        authorized=event.authorized,
        reason=event.reason,
        note=event.note,
        source=event.source,
        occurred_at=_as_utc(event.occurred_at),
        offline=event.offline,
    )


def access_event_item(session: Session, event: AccessEvent) -> AccessEventItem:
    """Build the enriched view (member and plan) of a single access event."""
    member = session.get(Member, event.member_id) if event.member_id is not None else None
    plan_name = None
    if event.member_id is not None:
        plan_name = session.exec(
            select(Plan.name)
            .join(Membership, Membership.plan_id == Plan.id)
            .where(Membership.member_id == event.member_id)
            .order_by(Membership.created_at.desc(), Membership.id.desc())
            .limit(1)
        ).first()
    return _build_access_event_item(event, member, plan_name)


def _access_event_summary(session: Session) -> AccessEventSummary:
    statement = select(
        func.count(AccessEvent.id),
        func.coalesce(
            func.sum(case((and_(AccessEvent.source != "manual", AccessEvent.authorized.is_(True)), 1), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(case((and_(AccessEvent.source != "manual", AccessEvent.authorized.is_(False)), 1), else_=0)),
            0,
        ),
        func.coalesce(func.sum(case((AccessEvent.source == "manual", 1), else_=0)), 0),
    )
    row = session.exec(statement).one()
    return AccessEventSummary(
        total=int(row[0] or 0),
        authorized=int(row[1] or 0),
        denied=int(row[2] or 0),
        manual=int(row[3] or 0),
    )


def access_today_summary(
    session: Session,
    *,
    timezone_name: str = DEFAULT_TIMEZONE,
    now: datetime | None = None,
) -> AccessTodaySummary:
    """Count today's authorized entries and denials in the gym's local day."""
    moment = _as_utc(now or utc_now())
    local_timezone = club_timezone(timezone_name)
    local_now = moment.astimezone(local_timezone)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_local.astimezone(timezone.utc)
    end = (start_local + timedelta(days=1)).astimezone(timezone.utc)

    statement = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (and_(AccessEvent.authorized.is_(True), AccessEvent.direction == AccessDirection.ENTRY.value), 1),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(func.sum(case((AccessEvent.authorized.is_(False), 1), else_=0)), 0),
        )
        .where(AccessEvent.occurred_at >= start, AccessEvent.occurred_at < end)
    )
    row = session.exec(statement).one()
    return AccessTodaySummary(entries=int(row[0] or 0), denied=int(row[1] or 0))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)