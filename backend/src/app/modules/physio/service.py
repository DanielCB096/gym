"""Physiotherapy catalog, pack sales and the reception agenda.

The module has one accounting rule, and everything here enforces it: an
appointment moves money and balance only when it is marked as attended.

* A **pack** is a prepaid balance: one sale at purchase, then one credit per
  attended session. It is never a subscription and it never renews itself.
* A **single session** is charged when the member shows up, not when the slot
  is booked. The charge is a regular service sale (SKU ``FISIO``) linked back
  to the appointment, so the register shift, the member account, the revenue
  report and invoicing keep working with no parallel ledger.
* A **no-show** or a **cancellation** touches neither money nor balance. That
  is why there is no penalty and no debt: the club only charges what it
  delivered.

Attendance can be corrected during the same window (from the start of the
appointment until 24 hours after it ends): turning ``attended`` back into
``no_show`` refunds the charge or returns the credit, and the reverse charges
or consumes again. Outside that window the mark is final. The appointment and
the pack are read with ``SELECT ... FOR UPDATE`` so a double click cannot charge
twice; the lock is real on PostgreSQL and a no-op on the SQLite used by tests.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.identity.models import Employee
from app.modules.inventory.models import Sale
from app.modules.inventory.service import (
    InventoryError,
    refund_service_sale,
    register_service_sale,
    service_sale_for_physio_appointment,
)
from app.modules.memberships.models import Member
from app.modules.notifications.service import (
    notify_physio_appointment_cancelled,
    notify_physio_appointment_rescheduled,
    notify_physio_appointment_scheduled,
)
from app.modules.physio.models import (
    APPOINTMENT_STATUSES,
    ATTENDANCE_GRACE_HOURS,
    DEFAULT_VALIDITY_DAYS,
    MAX_ADJUSTMENT_REASON_CHARS,
    PhysioAppointment,
    PhysioOffer,
    PhysioPack,
    PhysioPackAdjustment,
    PhysioRoom,
    PhysioService,
    PhysioSpecialty,
    PhysioTherapistProfile,
    utc_now,
)
from app.timezone import club_timezone, local_midnight

PHYSIO_SKU = "FISIO"

MAX_DURATION_MINUTES = 480
MAX_SESSIONS = 52
MAX_VALIDITY_DAYS = 366
MAX_PRICE_CENTS = 10_000_000

# Sentinel so a partial update can tell "leave unchanged" (absent) apart from
# "clear the value" (explicit ``None``).
UNSET: object = object()


class PhysioError(Exception):
    """Base class for every expected physiotherapy-module failure."""


class InvalidPhysioData(PhysioError):
    pass


class DuplicatePhysioCode(PhysioError):
    pass


class DuplicatePhysioOffer(PhysioError):
    pass


class PhysioServiceNotFound(PhysioError):
    pass


class PhysioOfferNotFound(PhysioError):
    pass


class PhysioAppointmentNotFound(PhysioError):
    pass


class PhysioPackNotFound(PhysioError):
    pass


class PhysioRoomNotFound(PhysioError):
    pass


class PhysioSpecialtyNotFound(PhysioError):
    pass


class DuplicatePhysioRoom(PhysioError):
    pass


class DuplicatePhysioSpecialty(PhysioError):
    pass


class InvalidPhysioAdjustment(PhysioError):
    pass


class PhysioMemberUnavailable(PhysioError):
    pass


class PhysioTherapistUnavailable(PhysioError):
    pass


class PhysioSlotConflict(PhysioError):
    pass


class InvalidPhysioState(PhysioError):
    pass


class PhysioChargeFailed(PhysioError):
    pass


@dataclass(frozen=True)
class PhysioServiceItem:
    id: UUID
    code: str
    name: str
    description: str | None
    duration_minutes: int
    price_cents: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PhysioOfferItem:
    id: UUID
    service_id: UUID
    service_name: str
    name: str
    sessions: int
    price_cents: int
    list_price_cents: int
    savings_cents: int
    discount_percent: int
    validity_days: int
    payment_mode: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PhysioTherapistItem:
    id: UUID
    name: str
    job_title: str
    specialty_id: UUID | None
    specialty_name: str | None
    room_id: UUID | None
    room_name: str | None


@dataclass(frozen=True)
class PhysioRoomItem:
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PhysioSpecialtyItem:
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PhysioPackItem:
    id: UUID
    member_id: UUID
    member_name: str
    offer_id: UUID
    offer_name: str
    service_id: UUID
    service_name: str
    sale_id: UUID
    sessions_total: int
    sessions_used: int
    remaining_sessions: int
    price_cents: int
    purchased_at: datetime
    valid_until: datetime
    status: str
    extended_days: int
    voided_at: datetime | None
    voided_sessions: int
    void_reason: str | None


@dataclass(frozen=True)
class PhysioPackAdjustmentItem:
    id: UUID
    pack_id: UUID
    kind: str
    days: int | None
    reason: str
    actor_id: UUID | None
    created_at: datetime


@dataclass(frozen=True)
class PhysioPackDetailItem:
    pack: PhysioPackItem
    adjustments: list[PhysioPackAdjustmentItem]


@dataclass(frozen=True)
class PhysioAppointmentItem:
    id: UUID
    member_id: UUID
    member_name: str
    service_id: UUID
    service_name: str
    service_price_cents: int
    pack_id: UUID | None
    pack_remaining_sessions: int | None
    therapist_employee_id: UUID
    therapist_name: str
    room_id: UUID | None
    room: str | None
    starts_at: datetime
    ends_at: datetime
    status: str
    notes: str | None
    booked_by: UUID | None
    marked_at: datetime | None
    marked_by: UUID | None
    cancelled_at: datetime | None
    cancelled_by: UUID | None
    created_at: datetime
    updated_at: datetime
    charge_sale_id: UUID | None
    charge_cents: int | None
    charge_payment_method: str | None
    charge_status: str | None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _member_name(member: Member | None) -> str:
    if member is None:
        return "Socio"
    return f"{member.first_name} {member.last_name}".strip()


def _employee_name(employee: Employee | None) -> str:
    if employee is None:
        return "Fisioterapeuta"
    return f"{employee.first_name} {employee.last_name}".strip()


def _pack_status(pack: PhysioPack, *, now: datetime) -> str:
    if pack.voided_at is not None:
        return "voided"
    remaining = pack.sessions_total - pack.sessions_used
    if remaining <= 0:
        return "exhausted"
    if _as_utc(pack.valid_until) < now:
        return "expired"
    return "active"


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


def _service_item(service: PhysioService) -> PhysioServiceItem:
    return PhysioServiceItem(
        id=service.id,
        code=service.code,
        name=service.name,
        description=service.description,
        duration_minutes=service.duration_minutes,
        price_cents=service.price_cents,
        is_active=service.is_active,
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


def list_physio_services(session: Session) -> list[PhysioServiceItem]:
    statement = select(PhysioService).order_by(PhysioService.name)
    return [_service_item(service) for service in session.exec(statement).all()]


def create_physio_service(
    session: Session,
    *,
    code: str,
    name: str,
    description: str | None = None,
    duration_minutes: int,
    price_cents: int,
    is_active: bool = True,
) -> PhysioServiceItem:
    normalized_code = (code or "").strip().upper()
    normalized_name = (name or "").strip()
    if not normalized_code or len(normalized_code) > 40:
        raise InvalidPhysioData("El código del servicio es obligatorio (máximo 40 caracteres)")
    if not normalized_name or len(normalized_name) > 160:
        raise InvalidPhysioData("El nombre del servicio es obligatorio (máximo 160 caracteres)")
    if duration_minutes < 1 or duration_minutes > MAX_DURATION_MINUTES:
        raise InvalidPhysioData(
            f"La duración debe estar entre 1 y {MAX_DURATION_MINUTES} minutos"
        )
    if price_cents < 0 or price_cents > MAX_PRICE_CENTS:
        raise InvalidPhysioData("El precio del servicio no es válido")
    normalized_description = (description or "").strip() or None

    service = PhysioService(
        code=normalized_code,
        name=normalized_name,
        description=normalized_description,
        duration_minutes=duration_minutes,
        price_cents=price_cents,
        is_active=is_active,
    )
    session.add(service)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicatePhysioCode("Ya existe un servicio con ese código") from error
    session.commit()
    session.refresh(service)
    return _service_item(service)


def update_physio_service(
    session: Session,
    service_id: UUID,
    *,
    code: str | None = None,
    name: str | None = None,
    description: str | None | object = UNSET,
    duration_minutes: int | None = None,
    price_cents: int | None = None,
    is_active: bool | None = None,
) -> PhysioServiceItem:
    service = session.get(PhysioService, service_id)
    if service is None:
        raise PhysioServiceNotFound("El servicio no existe")

    if code is not None:
        normalized_code = code.strip().upper()
        if not normalized_code or len(normalized_code) > 40:
            raise InvalidPhysioData("El código del servicio es obligatorio (máximo 40 caracteres)")
        service.code = normalized_code
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 160:
            raise InvalidPhysioData("El nombre del servicio es obligatorio (máximo 160 caracteres)")
        service.name = normalized_name
    if description is not UNSET:
        normalized_description = (description or "").strip() or None
        service.description = normalized_description
    if duration_minutes is not None:
        if duration_minutes < 1 or duration_minutes > MAX_DURATION_MINUTES:
            raise InvalidPhysioData(
                f"La duración debe estar entre 1 y {MAX_DURATION_MINUTES} minutos"
            )
        service.duration_minutes = duration_minutes
    if price_cents is not None:
        if price_cents < 0 or price_cents > MAX_PRICE_CENTS:
            raise InvalidPhysioData("El precio del servicio no es válido")
        service.price_cents = price_cents
    if is_active is not None:
        service.is_active = is_active

    service.updated_at = utc_now()
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicatePhysioCode("Ya existe un servicio con ese código") from error
    session.commit()
    session.refresh(service)
    return _service_item(service)


def _offer_item(offer: PhysioOffer, service: PhysioService | None) -> PhysioOfferItem:
    savings = max(offer.list_price_cents - offer.price_cents, 0)
    discount = round(savings * 100 / offer.list_price_cents) if offer.list_price_cents else 0
    return PhysioOfferItem(
        id=offer.id,
        service_id=offer.service_id,
        service_name=service.name if service is not None else "Servicio",
        name=offer.name,
        sessions=offer.sessions,
        price_cents=offer.price_cents,
        list_price_cents=offer.list_price_cents,
        savings_cents=savings,
        discount_percent=discount,
        validity_days=offer.validity_days,
        payment_mode=offer.payment_mode,
        is_active=offer.is_active,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
    )


def _offer_rows(session: Session, *, offer_id: UUID | None = None):
    statement = select(PhysioOffer, PhysioService).join(
        PhysioService, PhysioService.id == PhysioOffer.service_id
    )
    if offer_id is not None:
        statement = statement.where(PhysioOffer.id == offer_id)
    statement = statement.order_by(PhysioOffer.name)
    return session.exec(statement).all()


def list_physio_offers(session: Session) -> list[PhysioOfferItem]:
    return [_offer_item(offer, service) for offer, service in _offer_rows(session)]


def create_physio_offer(
    session: Session,
    *,
    service_id: UUID,
    name: str,
    sessions: int,
    price_cents: int,
    validity_days: int = DEFAULT_VALIDITY_DAYS,
) -> PhysioOfferItem:
    service = session.get(PhysioService, service_id)
    if service is None:
        raise PhysioServiceNotFound("El servicio no existe")
    normalized_name = (name or "").strip()
    if not normalized_name or len(normalized_name) > 160:
        raise InvalidPhysioData("El nombre del paquete es obligatorio (máximo 160 caracteres)")
    if sessions < 1 or sessions > MAX_SESSIONS:
        raise InvalidPhysioData(f"El paquete debe tener entre 1 y {MAX_SESSIONS} sesiones")
    if validity_days < 1 or validity_days > MAX_VALIDITY_DAYS:
        raise InvalidPhysioData(f"La vigencia debe estar entre 1 y {MAX_VALIDITY_DAYS} días")
    if price_cents < 0 or price_cents > MAX_PRICE_CENTS:
        raise InvalidPhysioData("El precio del paquete no es válido")
    list_price_cents = service.price_cents * sessions
    if price_cents > list_price_cents:
        raise InvalidPhysioData(
            "El precio del paquete no puede ser mayor que la suma de las sesiones sueltas "
            f"({_money(list_price_cents)})"
        )

    offer = PhysioOffer(
        service_id=service.id,
        name=normalized_name,
        sessions=sessions,
        price_cents=price_cents,
        list_price_cents=list_price_cents,
        validity_days=validity_days,
        payment_mode="single",
    )
    session.add(offer)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicatePhysioOffer("Ya existe un paquete con ese nombre") from error
    session.commit()
    session.refresh(offer)
    return _offer_item(offer, service)


def update_physio_offer(
    session: Session,
    offer_id: UUID,
    *,
    name: str | None = None,
    sessions: int | None = None,
    price_cents: int | None = None,
    validity_days: int | None = None,
    is_active: bool | None = None,
) -> PhysioOfferItem:
    offer = session.get(PhysioOffer, offer_id)
    if offer is None:
        raise PhysioOfferNotFound("El paquete no existe")
    service = session.get(PhysioService, offer.service_id)
    if service is None:
        raise PhysioServiceNotFound("El servicio del paquete no existe")

    recompute_list = False
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 160:
            raise InvalidPhysioData("El nombre del paquete es obligatorio (máximo 160 caracteres)")
        offer.name = normalized_name
    if sessions is not None:
        if sessions < 1 or sessions > MAX_SESSIONS:
            raise InvalidPhysioData(f"El paquete debe tener entre 1 y {MAX_SESSIONS} sesiones")
        offer.sessions = sessions
        recompute_list = True
    if validity_days is not None:
        if validity_days < 1 or validity_days > MAX_VALIDITY_DAYS:
            raise InvalidPhysioData(f"La vigencia debe estar entre 1 y {MAX_VALIDITY_DAYS} días")
        offer.validity_days = validity_days
    if price_cents is not None:
        if price_cents < 0 or price_cents > MAX_PRICE_CENTS:
            raise InvalidPhysioData("El precio del paquete no es válido")
        offer.price_cents = price_cents
    if recompute_list:
        offer.list_price_cents = service.price_cents * offer.sessions
    if offer.price_cents > offer.list_price_cents:
        raise InvalidPhysioData(
            "El precio del paquete no puede ser mayor que la suma de las sesiones sueltas "
            f"({_money(offer.list_price_cents)})"
        )
    if is_active is not None:
        offer.is_active = is_active

    offer.updated_at = utc_now()
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicatePhysioOffer("Ya existe un paquete con ese nombre") from error
    session.commit()
    session.refresh(offer)
    return _offer_item(offer, service)


# --------------------------------------------------------------------------- #
# Rooms and specialties
# --------------------------------------------------------------------------- #


def _room_item(room: PhysioRoom) -> PhysioRoomItem:
    return PhysioRoomItem(
        id=room.id,
        name=room.name,
        is_active=room.is_active,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


def list_physio_rooms(session: Session) -> list[PhysioRoomItem]:
    statement = select(PhysioRoom).order_by(PhysioRoom.name)
    return [_room_item(room) for room in session.exec(statement).all()]


def create_physio_room(
    session: Session, *, name: str, is_active: bool = True
) -> PhysioRoomItem:
    normalized = (name or "").strip()
    if not normalized or len(normalized) > 80:
        raise InvalidPhysioData("El nombre del consultorio es obligatorio (máximo 80 caracteres)")
    room = PhysioRoom(name=normalized, is_active=is_active)
    session.add(room)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicatePhysioRoom("Ya existe un consultorio con ese nombre") from error
    session.commit()
    session.refresh(room)
    return _room_item(room)


def update_physio_room(
    session: Session,
    room_id: UUID,
    *,
    name: str | None = None,
    is_active: bool | None = None,
) -> PhysioRoomItem:
    room = session.get(PhysioRoom, room_id)
    if room is None:
        raise PhysioRoomNotFound("El consultorio no existe")
    if name is not None:
        normalized = name.strip()
        if not normalized or len(normalized) > 80:
            raise InvalidPhysioData(
                "El nombre del consultorio es obligatorio (máximo 80 caracteres)"
            )
        room.name = normalized
    if is_active is not None:
        room.is_active = is_active
    room.updated_at = utc_now()
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicatePhysioRoom("Ya existe un consultorio con ese nombre") from error
    session.commit()
    session.refresh(room)
    return _room_item(room)


def _specialty_item(specialty: PhysioSpecialty) -> PhysioSpecialtyItem:
    return PhysioSpecialtyItem(
        id=specialty.id,
        name=specialty.name,
        is_active=specialty.is_active,
        created_at=specialty.created_at,
        updated_at=specialty.updated_at,
    )


def list_physio_specialties(session: Session) -> list[PhysioSpecialtyItem]:
    statement = select(PhysioSpecialty).order_by(PhysioSpecialty.name)
    return [_specialty_item(specialty) for specialty in session.exec(statement).all()]


def create_physio_specialty(
    session: Session, *, name: str, is_active: bool = True
) -> PhysioSpecialtyItem:
    normalized = (name or "").strip()
    if not normalized or len(normalized) > 80:
        raise InvalidPhysioData("El nombre de la especialidad es obligatorio (máximo 80 caracteres)")
    specialty = PhysioSpecialty(name=normalized, is_active=is_active)
    session.add(specialty)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicatePhysioSpecialty("Ya existe una especialidad con ese nombre") from error
    session.commit()
    session.refresh(specialty)
    return _specialty_item(specialty)


def update_physio_specialty(
    session: Session,
    specialty_id: UUID,
    *,
    name: str | None = None,
    is_active: bool | None = None,
) -> PhysioSpecialtyItem:
    specialty = session.get(PhysioSpecialty, specialty_id)
    if specialty is None:
        raise PhysioSpecialtyNotFound("La especialidad no existe")
    if name is not None:
        normalized = name.strip()
        if not normalized or len(normalized) > 80:
            raise InvalidPhysioData(
                "El nombre de la especialidad es obligatorio (máximo 80 caracteres)"
            )
        specialty.name = normalized
    if is_active is not None:
        specialty.is_active = is_active
    specialty.updated_at = utc_now()
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicatePhysioSpecialty("Ya existe una especialidad con ese nombre") from error
    session.commit()
    session.refresh(specialty)
    return _specialty_item(specialty)


def _require_room(session: Session, room_id: UUID) -> PhysioRoom:
    room = session.get(PhysioRoom, room_id)
    if room is None:
        raise PhysioRoomNotFound("El consultorio no existe")
    if not room.is_active:
        raise InvalidPhysioState("El consultorio está desactivado")
    return room


def _require_specialty(session: Session, specialty_id: UUID) -> PhysioSpecialty:
    specialty = session.get(PhysioSpecialty, specialty_id)
    if specialty is None:
        raise PhysioSpecialtyNotFound("La especialidad no existe")
    if not specialty.is_active:
        raise InvalidPhysioState("La especialidad está desactivada")
    return specialty


# --------------------------------------------------------------------------- #
# Packs
# --------------------------------------------------------------------------- #


def _pack_rows(session: Session, *, member_id: UUID | None = None, pack_id: UUID | None = None):
    statement = (
        select(
            PhysioPack,
            Member.first_name,
            Member.last_name,
            PhysioOffer.name,
            PhysioOffer.service_id,
            PhysioService.name,
        )
        .join(Member, Member.id == PhysioPack.member_id)
        .join(PhysioOffer, PhysioOffer.id == PhysioPack.offer_id)
        .join(PhysioService, PhysioService.id == PhysioOffer.service_id)
    )
    if member_id is not None:
        statement = statement.where(PhysioPack.member_id == member_id)
    if pack_id is not None:
        statement = statement.where(PhysioPack.id == pack_id)
    statement = statement.order_by(PhysioPack.valid_until.asc(), PhysioPack.purchased_at.desc())
    return session.exec(statement).all()


def _extension_days(session: Session, pack_ids: list[UUID]) -> dict[UUID, int]:
    if not pack_ids:
        return {}
    rows = session.exec(
        select(PhysioPackAdjustment.pack_id, PhysioPackAdjustment.days).where(
            PhysioPackAdjustment.pack_id.in_(pack_ids),
            PhysioPackAdjustment.kind == "extension",
        )
    ).all()
    totals: dict[UUID, int] = {}
    for pack_id, days in rows:
        totals[pack_id] = totals.get(pack_id, 0) + (days or 0)
    return totals


def _pack_item(row, *, now: datetime, extended_days: int = 0) -> PhysioPackItem:
    pack, first_name, last_name, offer_name, service_id, service_name = row
    remaining = max(pack.sessions_total - pack.sessions_used, 0)
    if pack.voided_at is not None:
        remaining = 0
    return PhysioPackItem(
        id=pack.id,
        member_id=pack.member_id,
        member_name=f"{first_name} {last_name}".strip(),
        offer_id=pack.offer_id,
        offer_name=offer_name,
        service_id=service_id,
        service_name=service_name,
        sale_id=pack.sale_id,
        sessions_total=pack.sessions_total,
        sessions_used=pack.sessions_used,
        remaining_sessions=remaining,
        price_cents=pack.price_cents,
        purchased_at=pack.purchased_at,
        valid_until=pack.valid_until,
        status=_pack_status(pack, now=now),
        extended_days=extended_days,
        voided_at=pack.voided_at,
        voided_sessions=pack.voided_sessions,
        void_reason=pack.void_reason,
    )


def list_physio_packs(
    session: Session,
    *,
    member_id: UUID,
    now: datetime | None = None,
) -> list[PhysioPackItem]:
    occurred = _as_utc(now or utc_now())
    rows = _pack_rows(session, member_id=member_id)
    extensions = _extension_days(session, [row[0].id for row in rows])
    return [
        _pack_item(row, now=occurred, extended_days=extensions.get(row[0].id, 0))
        for row in rows
    ]


def _adjustment_item(adjustment: PhysioPackAdjustment) -> PhysioPackAdjustmentItem:
    return PhysioPackAdjustmentItem(
        id=adjustment.id,
        pack_id=adjustment.pack_id,
        kind=adjustment.kind,
        days=adjustment.days,
        reason=adjustment.reason,
        actor_id=adjustment.actor_id,
        created_at=adjustment.created_at,
    )


def get_physio_pack(
    session: Session, pack_id: UUID, *, now: datetime | None = None
) -> PhysioPackDetailItem:
    rows = _pack_rows(session, pack_id=pack_id)
    if not rows:
        raise PhysioPackNotFound("El paquete no existe")
    occurred = _as_utc(now or utc_now())
    adjustments = session.exec(
        select(PhysioPackAdjustment)
        .where(PhysioPackAdjustment.pack_id == pack_id)
        .order_by(PhysioPackAdjustment.created_at, PhysioPackAdjustment.id)
    ).all()
    extensions = sum(
        adjustment.days or 0
        for adjustment in adjustments
        if adjustment.kind == "extension"
    )
    return PhysioPackDetailItem(
        pack=_pack_item(rows[0], now=occurred, extended_days=extensions),
        adjustments=[_adjustment_item(adjustment) for adjustment in adjustments],
    )


def sell_physio_pack(
    session: Session,
    *,
    member_id: UUID,
    offer_id: UUID,
    payment_method: str,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> PhysioPackItem:
    """Sell a pack as one service sale and create its two credits.

    The sale is the only money record; the pack is the balance it bought. Both
    are written in the same transaction, so a pack can never exist unpaid.
    """
    member = session.get(Member, member_id)
    if member is None:
        raise PhysioMemberUnavailable("Socio no encontrado")
    if member.status == "inactive":
        raise PhysioMemberUnavailable("El socio está inactivo y no puede comprar un paquete")

    offer = session.get(PhysioOffer, offer_id)
    if offer is None:
        raise PhysioOfferNotFound("El paquete no existe")
    if not offer.is_active:
        raise InvalidPhysioState("El paquete está desactivado y no se puede vender")
    service = session.get(PhysioService, offer.service_id)
    if service is None:
        raise PhysioServiceNotFound("El servicio del paquete no existe")
    if not service.is_active:
        raise InvalidPhysioState("El servicio está desactivado y no se puede vender")

    occurred = _as_utc(now or utc_now())
    try:
        sale = register_service_sale(
            session,
            member_id=member.id,
            description=f"Paquete de fisioterapia: {offer.name}"[:160],
            amount_cents=offer.price_cents,
            payment_method=payment_method,
            cashier_id=actor_id,
            sku=PHYSIO_SKU,
            now=occurred,
        )
    except InventoryError as error:
        raise PhysioChargeFailed(str(error)) from error

    pack = PhysioPack(
        member_id=member.id,
        offer_id=offer.id,
        sale_id=sale.id,
        sessions_total=offer.sessions,
        sessions_used=0,
        price_cents=offer.price_cents,
        purchased_at=occurred,
        valid_until=occurred + timedelta(days=offer.validity_days),
    )
    session.add(pack)
    session.commit()
    session.refresh(pack)
    rows = _pack_rows(session, pack_id=pack.id)
    if not rows:
        raise PhysioError("No se pudo leer el paquete recién creado")
    return _pack_item(rows[0], now=occurred)


@dataclass(frozen=True)
class PhysioPackVoidItem:
    pack: PhysioPackItem
    adjustments: list[PhysioPackAdjustmentItem]
    cancelled_appointments: int


def _validate_adjustment_reason(reason: str | None) -> str:
    normalized = (reason or "").strip()
    if not normalized or len(normalized) > MAX_ADJUSTMENT_REASON_CHARS:
        raise InvalidPhysioAdjustment(
            "El motivo es obligatorio (máximo "
            f"{MAX_ADJUSTMENT_REASON_CHARS} caracteres)"
        )
    return normalized


def extend_physio_pack(
    session: Session,
    pack_id: UUID,
    *,
    days: int,
    reason: str,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> PhysioPackDetailItem:
    """Push the expiry of a pack without touching its credits or the sale.

    An expired pack is extended from today, not from its old expiry, so the
    extension always buys future days. The adjustment is audited.
    """
    pack = session.exec(
        select(PhysioPack).where(PhysioPack.id == pack_id).with_for_update()
    ).first()
    if pack is None:
        raise PhysioPackNotFound("El paquete no existe")
    if pack.voided_at is not None:
        raise InvalidPhysioState("Un paquete anulado no se puede extender")
    if days < 1 or days > MAX_VALIDITY_DAYS:
        raise InvalidPhysioAdjustment(
            f"La extensión debe estar entre 1 y {MAX_VALIDITY_DAYS} días"
        )
    normalized_reason = _validate_adjustment_reason(reason)
    occurred = _as_utc(now or utc_now())
    base = max(_as_utc(pack.valid_until), occurred)
    pack.valid_until = base + timedelta(days=days)
    session.add(pack)
    session.add(
        PhysioPackAdjustment(
            pack_id=pack.id,
            kind="extension",
            days=days,
            reason=normalized_reason,
            actor_id=actor_id,
            created_at=occurred,
        )
    )
    session.commit()
    return get_physio_pack(session, pack.id, now=occurred)


def void_physio_pack(
    session: Session,
    pack_id: UUID,
    *,
    reason: str,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> PhysioPackVoidItem:
    """Cancel the remaining credits of a pack and its future appointments.

    The money is not refunded: voiding is an administrative correction (a pack
    sold by mistake or granted as courtesy). The remaining credits are recorded
    in ``voided_sessions`` instead of being marked as used, and every future
    appointment covered by the pack is cancelled with its notice.
    """
    pack = session.exec(
        select(PhysioPack).where(PhysioPack.id == pack_id).with_for_update()
    ).first()
    if pack is None:
        raise PhysioPackNotFound("El paquete no existe")
    if pack.voided_at is not None:
        raise InvalidPhysioState("El paquete ya está anulado")
    remaining = pack.sessions_total - pack.sessions_used
    if remaining <= 0:
        raise InvalidPhysioState("El paquete no tiene sesiones por anular")
    normalized_reason = _validate_adjustment_reason(reason)
    occurred = _as_utc(now or utc_now())

    pack.voided_at = occurred
    pack.voided_by = actor_id
    pack.void_reason = normalized_reason
    pack.voided_sessions = remaining
    session.add(pack)
    session.add(
        PhysioPackAdjustment(
            pack_id=pack.id,
            kind="void",
            days=None,
            reason=normalized_reason,
            actor_id=actor_id,
            created_at=occurred,
        )
    )

    future = session.exec(
        select(PhysioAppointment).where(
            PhysioAppointment.pack_id == pack.id,
            PhysioAppointment.status == "scheduled",
            PhysioAppointment.starts_at > occurred,
        )
    ).all()
    for appointment in future:
        appointment.status = "cancelled"
        appointment.cancelled_at = occurred
        appointment.cancelled_by = actor_id
        appointment.updated_at = occurred
        session.add(appointment)
        service = session.get(PhysioService, appointment.service_id)
        if service is not None:
            notify_physio_appointment_cancelled(
                session,
                member_id=appointment.member_id,
                appointment_id=appointment.id,
                service_name=service.name,
                starts_at=appointment.starts_at,
                now=occurred,
            )
    session.commit()
    detail = get_physio_pack(session, pack.id, now=occurred)
    return PhysioPackVoidItem(
        pack=detail.pack,
        adjustments=detail.adjustments,
        cancelled_appointments=len(future),
    )


# --------------------------------------------------------------------------- #
# Agenda
# --------------------------------------------------------------------------- #


def _therapist_rows(session: Session, *, employee_id: UUID | None = None):
    statement = (
        select(Employee, PhysioSpecialty.name, PhysioRoom.name, PhysioTherapistProfile)
        .outerjoin(
            PhysioTherapistProfile,
            PhysioTherapistProfile.employee_id == Employee.id,
        )
        .outerjoin(
            PhysioSpecialty, PhysioSpecialty.id == PhysioTherapistProfile.specialty_id
        )
        .outerjoin(PhysioRoom, PhysioRoom.id == PhysioTherapistProfile.room_id)
    )
    if employee_id is not None:
        statement = statement.where(Employee.id == employee_id)
    else:
        statement = statement.where(Employee.status == "active")
    statement = statement.order_by(Employee.first_name, Employee.last_name)
    return session.exec(statement).all()


def _therapist_item(row) -> PhysioTherapistItem:
    employee, specialty_name, room_name, profile = row
    return PhysioTherapistItem(
        id=employee.id,
        name=_employee_name(employee),
        job_title=employee.job_title,
        specialty_id=profile.specialty_id if profile is not None else None,
        specialty_name=specialty_name,
        room_id=profile.room_id if profile is not None else None,
        room_name=room_name,
    )


def list_physio_therapists(session: Session) -> list[PhysioTherapistItem]:
    return [_therapist_item(row) for row in _therapist_rows(session)]


def update_physio_therapist_profile(
    session: Session,
    employee_id: UUID,
    *,
    specialty_id: UUID | None | object = UNSET,
    room_id: UUID | None | object = UNSET,
) -> PhysioTherapistItem:
    """Attach a specialty and a default room to an employee of the room."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise PhysioTherapistUnavailable("El fisioterapeuta no existe")

    if specialty_id is not UNSET and specialty_id is not None:
        _require_specialty(session, specialty_id)
    if room_id is not UNSET and room_id is not None:
        _require_room(session, room_id)

    profile = session.exec(
        select(PhysioTherapistProfile).where(
            PhysioTherapistProfile.employee_id == employee_id
        )
    ).first()
    if profile is None:
        profile = PhysioTherapistProfile(employee_id=employee_id)
        session.add(profile)
    if specialty_id is not UNSET:
        profile.specialty_id = specialty_id
    if room_id is not UNSET:
        profile.room_id = room_id
    profile.updated_at = utc_now()
    session.commit()
    rows = _therapist_rows(session, employee_id=employee_id)
    if not rows:
        raise PhysioTherapistUnavailable("El fisioterapeuta no existe")
    return _therapist_item(rows[0])


def _appointment_rows(
    session: Session,
    *,
    appointment_id: UUID | None = None,
    appointment_ids: list[UUID] | None = None,
    day: date | None = None,
    therapist_id: UUID | None = None,
    status: str | None = None,
    timezone_name: str | None = None,
):
    statement = (
        select(
            PhysioAppointment,
            Member.first_name,
            Member.last_name,
            PhysioService.name,
            PhysioService.price_cents,
            Employee.first_name,
            Employee.last_name,
            PhysioPack.sessions_total,
            PhysioPack.sessions_used,
        )
        .join(Member, Member.id == PhysioAppointment.member_id)
        .join(PhysioService, PhysioService.id == PhysioAppointment.service_id)
        .join(Employee, Employee.id == PhysioAppointment.therapist_employee_id)
        .outerjoin(PhysioPack, PhysioPack.id == PhysioAppointment.pack_id)
    )
    if appointment_id is not None:
        statement = statement.where(PhysioAppointment.id == appointment_id)
    if appointment_ids is not None:
        statement = statement.where(PhysioAppointment.id.in_(appointment_ids))
    if day is not None:
        tz = club_timezone(timezone_name)
        starts = local_midnight(day, tz)
        ends = local_midnight(day + timedelta(days=1), tz)
        statement = statement.where(
            PhysioAppointment.starts_at >= starts,
            PhysioAppointment.starts_at < ends,
        )
    if therapist_id is not None:
        statement = statement.where(
            PhysioAppointment.therapist_employee_id == therapist_id
        )
    if status is not None:
        statement = statement.where(PhysioAppointment.status == status)
    statement = statement.order_by(PhysioAppointment.starts_at)
    return session.exec(statement).all()


def _latest_charges(session: Session, appointment_ids: list[UUID]) -> dict[UUID, Sale]:
    if not appointment_ids:
        return {}
    sales = session.exec(
        select(Sale)
        .where(Sale.physio_appointment_id.in_(appointment_ids))
        .order_by(Sale.sold_at.asc(), Sale.created_at.asc())
    ).all()
    latest: dict[UUID, Sale] = {}
    for sale in sales:
        latest[sale.physio_appointment_id] = sale
    return latest


def _appointment_item(row, charge: Sale | None) -> PhysioAppointmentItem:
    (
        appointment,
        member_first,
        member_last,
        service_name,
        service_price_cents,
        therapist_first,
        therapist_last,
        pack_total,
        pack_used,
    ) = row
    return PhysioAppointmentItem(
        id=appointment.id,
        member_id=appointment.member_id,
        member_name=f"{member_first} {member_last}".strip(),
        service_id=appointment.service_id,
        service_name=service_name,
        service_price_cents=service_price_cents,
        pack_id=appointment.pack_id,
        pack_remaining_sessions=(
            max(pack_total - pack_used, 0) if pack_total is not None else None
        ),
        therapist_employee_id=appointment.therapist_employee_id,
        therapist_name=f"{therapist_first} {therapist_last}".strip(),
        room_id=appointment.room_id,
        room=appointment.room,
        starts_at=appointment.starts_at,
        ends_at=appointment.ends_at,
        status=appointment.status,
        notes=appointment.notes,
        booked_by=appointment.booked_by,
        marked_at=appointment.marked_at,
        marked_by=appointment.marked_by,
        cancelled_at=appointment.cancelled_at,
        cancelled_by=appointment.cancelled_by,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
        charge_sale_id=charge.id if charge is not None else None,
        charge_cents=charge.total_cents if charge is not None else None,
        charge_payment_method=charge.payment_method if charge is not None else None,
        charge_status=charge.status if charge is not None else None,
    )


def _appointment_item_by_id(
    session: Session, appointment_id: UUID, *, charge: Sale | None = None
) -> PhysioAppointmentItem:
    rows = _appointment_rows(session, appointment_id=appointment_id)
    if not rows:
        raise PhysioAppointmentNotFound("La cita no existe")
    if charge is None:
        charge = service_sale_for_physio_appointment(session, appointment_id)
    return _appointment_item(rows[0], charge)


def list_physio_appointments(
    session: Session,
    *,
    day: date | None = None,
    therapist_id: UUID | None = None,
    status: str | None = None,
    timezone_name: str | None = None,
) -> list[PhysioAppointmentItem]:
    if status is not None and status not in APPOINTMENT_STATUSES:
        raise InvalidPhysioData("Estado de cita no válido")
    rows = _appointment_rows(
        session,
        day=day,
        therapist_id=therapist_id,
        status=status,
        timezone_name=timezone_name,
    )
    charges = _latest_charges(session, [row[0].id for row in rows])
    return [_appointment_item(row, charges.get(row[0].id)) for row in rows]


def _resolve_pack_for(
    session: Session,
    *,
    member_id: UUID,
    service_id: UUID,
    at: datetime,
    lock: bool = False,
) -> PhysioPack | None:
    """The pack that should cover a session at ``at``: the first one to expire."""
    statement = (
        select(PhysioPack)
        .join(PhysioOffer, PhysioOffer.id == PhysioPack.offer_id)
        .where(
            PhysioPack.member_id == member_id,
            PhysioOffer.service_id == service_id,
            PhysioPack.sessions_used < PhysioPack.sessions_total,
            PhysioPack.valid_until >= at,
            PhysioPack.voided_at.is_(None),
        )
        .order_by(PhysioPack.valid_until.asc(), PhysioPack.purchased_at.asc())
    )
    if lock:
        statement = statement.with_for_update()
    return session.exec(statement).first()


def _assert_slot_free(
    session: Session,
    *,
    therapist_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    exclude_id: UUID | None = None,
) -> None:
    statement = select(PhysioAppointment.id).where(
        PhysioAppointment.therapist_employee_id == therapist_id,
        PhysioAppointment.status != "cancelled",
        PhysioAppointment.starts_at < ends_at,
        PhysioAppointment.ends_at > starts_at,
    )
    if exclude_id is not None:
        statement = statement.where(PhysioAppointment.id != exclude_id)
    if session.exec(statement).first() is not None:
        raise PhysioSlotConflict(
            "El fisioterapeuta ya tiene una cita que se encima con ese horario"
        )


def _validate_therapist(session: Session, therapist_id: UUID) -> Employee:
    therapist = session.get(Employee, therapist_id)
    if therapist is None or therapist.status != "active":
        raise PhysioTherapistUnavailable(
            "El fisioterapeuta no existe o ya no está activo"
        )
    return therapist


def create_physio_appointment(
    session: Session,
    *,
    member_id: UUID,
    service_id: UUID,
    therapist_employee_id: UUID,
    starts_at: datetime,
    room_id: UUID | None = None,
    room: str | None = None,
    notes: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> PhysioAppointmentItem:
    member = session.get(Member, member_id)
    if member is None:
        raise PhysioMemberUnavailable("Socio no encontrado")
    if member.status == "inactive":
        raise PhysioMemberUnavailable("El socio está inactivo y no puede agendar una cita")

    service = session.get(PhysioService, service_id)
    if service is None:
        raise PhysioServiceNotFound("El servicio no existe")
    if not service.is_active:
        raise InvalidPhysioState("El servicio está desactivado")

    therapist = _validate_therapist(session, therapist_employee_id)

    start = _as_utc(starts_at)
    end = start + timedelta(minutes=service.duration_minutes)
    normalized_room = (room or "").strip()[:80] or None
    resolved_room_id = room_id
    if room_id is not None:
        selected_room = _require_room(session, room_id)
        normalized_room = selected_room.name
    elif normalized_room is None:
        # Fall back to the therapist's default room when the agenda did not
        # choose one, so a small clinic does not have to repeat it each time.
        profile = session.exec(
            select(PhysioTherapistProfile).where(
                PhysioTherapistProfile.employee_id == therapist_employee_id
            )
        ).first()
        if profile is not None and profile.room_id is not None:
            default_room = session.get(PhysioRoom, profile.room_id)
            if default_room is not None and default_room.is_active:
                resolved_room_id = default_room.id
                normalized_room = default_room.name
    normalized_notes = (notes or "").strip() or None

    _assert_slot_free(
        session,
        therapist_id=therapist_employee_id,
        starts_at=start,
        ends_at=end,
    )
    pack = _resolve_pack_for(
        session,
        member_id=member.id,
        service_id=service.id,
        at=start,
    )

    appointment = PhysioAppointment(
        member_id=member.id,
        service_id=service.id,
        pack_id=pack.id if pack is not None else None,
        therapist_employee_id=therapist_employee_id,
        room_id=resolved_room_id,
        room=normalized_room,
        starts_at=start,
        ends_at=end,
        status="scheduled",
        notes=normalized_notes,
        booked_by=actor_id,
    )
    session.add(appointment)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise PhysioSlotConflict(
            "El fisioterapeuta ya tiene una cita que empieza a esa misma hora"
        ) from error
    notify_physio_appointment_scheduled(
        session,
        member_id=member.id,
        appointment_id=appointment.id,
        service_name=service.name,
        therapist_name=_employee_name(therapist),
        starts_at=start,
    )
    session.commit()
    session.refresh(appointment)
    return _appointment_item_by_id(session, appointment.id)


def move_physio_appointment(
    session: Session,
    appointment_id: UUID,
    *,
    starts_at: datetime | None = None,
    therapist_employee_id: UUID | None = None,
    room_id: UUID | None | object = UNSET,
    room: str | None | object = UNSET,
    notes: str | None | object = UNSET,
    now: datetime | None = None,
) -> PhysioAppointmentItem:
    appointment = session.exec(
        select(PhysioAppointment)
        .where(PhysioAppointment.id == appointment_id)
        .with_for_update()
    ).first()
    if appointment is None:
        raise PhysioAppointmentNotFound("La cita no existe")
    if appointment.status != "scheduled":
        raise InvalidPhysioState("Solo se puede mover una cita pendiente")
    occurred = _as_utc(now or utc_now())
    if _as_utc(appointment.starts_at) <= occurred:
        raise InvalidPhysioState("La cita ya empezó y no se puede mover")

    service = session.get(PhysioService, appointment.service_id)
    if service is None:
        raise PhysioServiceNotFound("El servicio de la cita no existe")

    old_start = _as_utc(appointment.starts_at)
    old_end = _as_utc(appointment.ends_at)
    new_start = _as_utc(starts_at) if starts_at is not None else _as_utc(appointment.starts_at)
    new_end = new_start + timedelta(minutes=service.duration_minutes)
    new_therapist = (
        therapist_employee_id
        if therapist_employee_id is not None
        else appointment.therapist_employee_id
    )
    if therapist_employee_id is not None:
        _validate_therapist(session, new_therapist)

    _assert_slot_free(
        session,
        therapist_id=new_therapist,
        starts_at=new_start,
        ends_at=new_end,
        exclude_id=appointment.id,
    )
    # Moving re-picks the pack: a pack that expired before the new date cannot
    # cover it, and another one may be valid.
    pack = _resolve_pack_for(
        session,
        member_id=appointment.member_id,
        service_id=appointment.service_id,
        at=new_start,
    )

    appointment.starts_at = new_start
    appointment.ends_at = new_end
    appointment.therapist_employee_id = new_therapist
    appointment.pack_id = pack.id if pack is not None else None
    if room_id is not UNSET:
        if room_id is None:
            appointment.room_id = None
            if room is UNSET:
                appointment.room = None
        else:
            selected_room = _require_room(session, room_id)
            appointment.room_id = selected_room.id
            appointment.room = selected_room.name
    elif room is not UNSET:
        appointment.room_id = None
        appointment.room = (room or "").strip()[:80] or None
    if notes is not UNSET:
        appointment.notes = (notes or "").strip() or None
    appointment.updated_at = occurred
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise PhysioSlotConflict(
            "El fisioterapeuta ya tiene una cita que empieza a esa misma hora"
        ) from error
    if new_start != old_start or new_end != old_end:
        notify_physio_appointment_rescheduled(
            session,
            member_id=appointment.member_id,
            appointment_id=appointment.id,
            service_name=service.name,
            old_starts_at=old_start,
            starts_at=new_start,
            now=occurred,
        )
    session.commit()
    session.refresh(appointment)
    return _appointment_item_by_id(session, appointment.id)


def cancel_physio_appointment(
    session: Session,
    appointment_id: UUID,
    *,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> PhysioAppointmentItem:
    appointment = session.exec(
        select(PhysioAppointment)
        .where(PhysioAppointment.id == appointment_id)
        .with_for_update()
    ).first()
    if appointment is None:
        raise PhysioAppointmentNotFound("La cita no existe")
    if appointment.status != "scheduled":
        raise InvalidPhysioState("Solo se puede cancelar una cita pendiente")
    occurred = _as_utc(now or utc_now())
    if _as_utc(appointment.starts_at) <= occurred:
        raise InvalidPhysioState("La cita ya empezó y no se puede cancelar")

    service = session.get(PhysioService, appointment.service_id)
    if service is None:
        raise PhysioServiceNotFound("El servicio de la cita no existe")

    appointment.status = "cancelled"
    appointment.cancelled_at = occurred
    appointment.cancelled_by = actor_id
    appointment.updated_at = occurred
    session.add(appointment)
    notify_physio_appointment_cancelled(
        session,
        member_id=appointment.member_id,
        appointment_id=appointment.id,
        service_name=service.name,
        starts_at=appointment.starts_at,
        now=occurred,
    )
    session.commit()
    session.refresh(appointment)
    return _appointment_item_by_id(session, appointment.id)


def _consume_or_charge(
    session: Session,
    appointment: PhysioAppointment,
    service: PhysioService,
    *,
    payment_method: str | None,
    actor_id: UUID | None,
    now: datetime,
) -> None:
    """Cover an attended session with a credit, or charge it as a single one."""
    existing = service_sale_for_physio_appointment(session, appointment.id)
    if existing is not None and existing.status == "completed":
        return

    if appointment.pack_id is not None:
        pack = session.exec(
            select(PhysioPack)
            .where(PhysioPack.id == appointment.pack_id)
            .with_for_update()
        ).first()
        if (
            pack is not None
            and pack.voided_at is None
            and pack.sessions_used < pack.sessions_total
            and _as_utc(pack.valid_until) >= _as_utc(appointment.starts_at)
        ):
            pack.sessions_used += 1
            session.add(pack)
            return

    # The linked pack ran out (or expired) between the booking and the visit:
    # look for another valid pack before asking to charge the single session.
    pack = _resolve_pack_for(
        session,
        member_id=appointment.member_id,
        service_id=appointment.service_id,
        at=_as_utc(appointment.starts_at),
        lock=True,
    )
    if pack is not None:
        pack.sessions_used += 1
        appointment.pack_id = pack.id
        session.add(pack)
        return

    appointment.pack_id = None
    if payment_method is None:
        raise PhysioChargeFailed(
            "Selecciona la forma de pago para cobrar la sesión suelta"
        )
    try:
        register_service_sale(
            session,
            member_id=appointment.member_id,
            description=f"Fisioterapia: {service.name}"[:160],
            amount_cents=service.price_cents,
            payment_method=payment_method,
            cashier_id=actor_id,
            physio_appointment_id=appointment.id,
            sku=PHYSIO_SKU,
            now=now,
        )
    except InventoryError as error:
        raise PhysioChargeFailed(str(error)) from error


def _reverse_attendance(
    session: Session,
    appointment: PhysioAppointment,
    *,
    actor_id: UUID | None,
    now: datetime,
) -> None:
    """Undo what the attended mark did: refund the sale or return the credit."""
    sale = service_sale_for_physio_appointment(session, appointment.id)
    if sale is not None and sale.status == "completed":
        try:
            refund_service_sale(
                session,
                sale.id,
                reason="La cita se marcó como inasistencia",
                actor_id=actor_id,
                now=now,
            )
        except InventoryError as error:
            raise PhysioChargeFailed(str(error)) from error
        return
    if appointment.pack_id is not None:
        pack = session.exec(
            select(PhysioPack)
            .where(PhysioPack.id == appointment.pack_id)
            .with_for_update()
        ).first()
        if pack is not None and pack.voided_at is None and pack.sessions_used > 0:
            pack.sessions_used -= 1
            session.add(pack)


def mark_physio_attendance(
    session: Session,
    appointment_id: UUID,
    *,
    attended: bool,
    payment_method: str | None = None,
    actor_id: UUID | None = None,
    now: datetime | None = None,
) -> PhysioAppointmentItem:
    appointment = session.exec(
        select(PhysioAppointment)
        .where(PhysioAppointment.id == appointment_id)
        .with_for_update()
    ).first()
    if appointment is None:
        raise PhysioAppointmentNotFound("La cita no existe")
    if appointment.status == "cancelled":
        raise InvalidPhysioState("Una cita cancelada no se puede marcar")

    occurred = _as_utc(now or utc_now())
    start = _as_utc(appointment.starts_at)
    latest = _as_utc(appointment.ends_at) + timedelta(hours=ATTENDANCE_GRACE_HOURS)
    if occurred < start:
        raise InvalidPhysioState("La cita aún no empieza; espera a la hora para marcarla")
    if occurred > latest:
        raise InvalidPhysioState(
            "La ventana para marcar la asistencia ya cerró (24 horas después del fin)"
        )

    service = session.get(PhysioService, appointment.service_id)
    if service is None:
        raise PhysioServiceNotFound("El servicio de la cita no existe")

    if attended:
        if appointment.status != "attended":
            _consume_or_charge(
                session,
                appointment,
                service,
                payment_method=payment_method,
                actor_id=actor_id,
                now=occurred,
            )
        appointment.status = "attended"
    else:
        if appointment.status == "attended":
            _reverse_attendance(session, appointment, actor_id=actor_id, now=occurred)
        appointment.status = "no_show"

    appointment.marked_at = occurred
    appointment.marked_by = actor_id
    appointment.updated_at = occurred
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return _appointment_item_by_id(session, appointment.id)


def close_physio_day(
    session: Session,
    *,
    day: date,
    actor_id: UUID | None = None,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> list[PhysioAppointmentItem]:
    """Mark as no-show every pending appointment of ``day`` that already ended.

    Closing the day never charges nor consumes: it only leaves the agenda clean
    and the history complete.
    """
    occurred = _as_utc(now or utc_now())
    tz = club_timezone(timezone_name)
    starts = local_midnight(day, tz)
    ends = local_midnight(day + timedelta(days=1), tz)
    appointments = session.exec(
        select(PhysioAppointment)
        .where(
            PhysioAppointment.status == "scheduled",
            PhysioAppointment.starts_at >= starts,
            PhysioAppointment.starts_at < ends,
            PhysioAppointment.ends_at < occurred,
        )
        .order_by(PhysioAppointment.starts_at)
    ).all()
    for appointment in appointments:
        appointment.status = "no_show"
        appointment.marked_at = occurred
        appointment.marked_by = actor_id
        appointment.updated_at = occurred
        session.add(appointment)
    session.commit()
    if not appointments:
        return []
    ids = [appointment.id for appointment in appointments]
    rows = _appointment_rows(session, appointment_ids=ids)
    charges = _latest_charges(session, ids)
    return [_appointment_item(row, charges.get(row[0].id)) for row in rows]
