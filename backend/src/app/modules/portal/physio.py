"""Member self-service view of the physiotherapy room.

Read-only by design: the agenda is run from reception, so the app only tells the
member how many sessions are left, when the next appointment is and what
happened in the ones already behind them. Nothing here books, moves or cancels;
the service layer that owns those rules is not touched from this module.

The pack balance is derived at read time from ``sessions_used``, ``sessions_total``
and ``valid_until``, exactly like the staff view does, so the two screens can
never disagree about a pack that ran out or expired.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_
from sqlmodel import Session, select

from app.modules.identity.models import Employee
from app.modules.memberships.models import Member
from app.modules.physio.models import (
    PhysioAppointment,
    PhysioOffer,
    PhysioPack,
    PhysioService,
    utc_now,
)
from app.modules.portal.service import MemberPortalError

DEFAULT_HISTORY_LIMIT = 10
MAX_HISTORY_LIMIT = 50


@dataclass(frozen=True)
class MemberPhysioPackItem:
    id: UUID
    offer_name: str
    service_name: str
    sessions_total: int
    sessions_used: int
    remaining_sessions: int
    price_cents: int
    purchased_at: datetime
    valid_until: datetime
    status: str


@dataclass(frozen=True)
class MemberPhysioAppointmentItem:
    id: UUID
    service_name: str
    therapist_name: str
    room: str | None
    starts_at: datetime
    ends_at: datetime
    status: str
    covered_by_pack: bool


@dataclass(frozen=True)
class MemberPhysioOverview:
    packs: list[MemberPhysioPackItem]
    next_appointment: MemberPhysioAppointmentItem | None
    history: list[MemberPhysioAppointmentItem]


def member_physio_overview(
    session: Session,
    member_id: UUID,
    *,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
    now: datetime | None = None,
) -> MemberPhysioOverview:
    """Everything the member needs to know about their physiotherapy sessions."""
    member = session.get(Member, member_id)
    if member is None:
        raise MemberPortalError("Socio no encontrado")
    occurred = _as_utc(now or utc_now())
    history_limit = min(max(history_limit, 1), MAX_HISTORY_LIMIT)

    next_row = _appointment_rows(
        session,
        member_id=member_id,
        scheduled_after=occurred,
        limit=1,
    )
    next_appointment = (
        _appointment_item(next_row[0]) if next_row else None
    )

    history_rows = _appointment_rows(
        session,
        member_id=member_id,
        up_to=occurred,
        exclude_id=next_appointment.id if next_appointment is not None else None,
        limit=history_limit,
        newest_first=True,
    )
    return MemberPhysioOverview(
        packs=_pack_items(session, member_id, now=occurred),
        next_appointment=next_appointment,
        history=[_appointment_item(row) for row in history_rows],
    )


def _pack_items(
    session: Session, member_id: UUID, *, now: datetime
) -> list[MemberPhysioPackItem]:
    rows = session.exec(
        select(PhysioPack, PhysioOffer.name, PhysioService.name)
        .join(PhysioOffer, PhysioOffer.id == PhysioPack.offer_id)
        .join(PhysioService, PhysioService.id == PhysioOffer.service_id)
        .where(PhysioPack.member_id == member_id)
        .order_by(PhysioPack.valid_until.asc(), PhysioPack.purchased_at.desc())
    ).all()
    items: list[MemberPhysioPackItem] = []
    for pack, offer_name, service_name in rows:
        remaining = max(pack.sessions_total - pack.sessions_used, 0)
        if pack.voided_at is not None:
            remaining = 0
        items.append(
            MemberPhysioPackItem(
                id=pack.id,
                offer_name=offer_name,
                service_name=service_name,
                sessions_total=pack.sessions_total,
                sessions_used=pack.sessions_used,
                remaining_sessions=remaining,
                price_cents=pack.price_cents,
                purchased_at=_as_utc(pack.purchased_at),
                valid_until=_as_utc(pack.valid_until),
                status=_pack_status(pack, remaining=remaining, now=now),
            )
        )
    return items


def _appointment_rows(
    session: Session,
    *,
    member_id: UUID,
    scheduled_after: datetime | None = None,
    up_to: datetime | None = None,
    exclude_id: UUID | None = None,
    limit: int,
    newest_first: bool = False,
):
    statement = (
        select(
            PhysioAppointment,
            PhysioService.name,
            Employee.first_name,
            Employee.last_name,
        )
        .join(PhysioService, PhysioService.id == PhysioAppointment.service_id)
        .join(Employee, Employee.id == PhysioAppointment.therapist_employee_id)
        .where(PhysioAppointment.member_id == member_id)
    )
    if scheduled_after is not None:
        statement = statement.where(
            PhysioAppointment.status == "scheduled",
            PhysioAppointment.starts_at > scheduled_after,
        )
    if up_to is not None:
        # A cancelled appointment is history even when its slot is still ahead:
        # the member should see it was called off instead of wondering.
        statement = statement.where(
            or_(
                PhysioAppointment.starts_at <= up_to,
                PhysioAppointment.status != "scheduled",
            )
        )
    # The two halves of the screen must not overlap, but the history window
    # already excludes the future pending slot; ``exclude_id`` keeps the list
    # correct even if a row fell in both predicates.
    if exclude_id is not None:
        statement = statement.where(PhysioAppointment.id != exclude_id)
    statement = statement.order_by(
        PhysioAppointment.starts_at.desc()
        if newest_first
        else PhysioAppointment.starts_at.asc()
    ).limit(limit)
    return session.exec(statement).all()


def _appointment_item(row) -> MemberPhysioAppointmentItem:
    appointment, service_name, therapist_first, therapist_last = row
    return MemberPhysioAppointmentItem(
        id=appointment.id,
        service_name=service_name,
        therapist_name=f"{therapist_first} {therapist_last}".strip(),
        room=appointment.room,
        starts_at=_as_utc(appointment.starts_at),
        ends_at=_as_utc(appointment.ends_at),
        status=appointment.status,
        covered_by_pack=appointment.pack_id is not None,
    )


def _pack_status(pack: PhysioPack, *, remaining: int, now: datetime) -> str:
    if pack.voided_at is not None:
        return "voided"
    if remaining <= 0:
        return "exhausted"
    if _as_utc(pack.valid_until) < now:
        return "expired"
    return "active"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
