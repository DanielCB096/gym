"""Demand, occupancy and revenue of the physiotherapy room.

The room runs on appointments, so its report is built from them instead of the
sales ledger: a session covered by a pack never produces a sale, and counting
only money would hide the work the room actually did. Revenue is still read
from the existing sales (single sessions linked to an appointment, packs by
their purchase) so it always matches the register and the revenue report.

Volume here is dozens of appointments a day, so the period is loaded and
grouped in Python; that keeps the local-day and local-hour buckets exact without
duplicating the SQL date helpers of the reports module.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session, select

from app.modules.identity.models import Employee
from app.modules.inventory.models import Sale, SaleReturn
from app.modules.physio.models import (
    PhysioAppointment,
    PhysioOffer,
    PhysioPack,
    PhysioPackAdjustment,
    PhysioService,
)
from app.modules.reports.service import ExportTable, ReportPeriod

# The occupancy denominator is an estimate: the room has no shift schedule, so
# every therapist with agenda in the period is assumed to work this many hours
# per local day. It is documented as such in the module page.
ROOM_HOURS_PER_DAY = 8
ROOM_MINUTES_PER_DAY = ROOM_HOURS_PER_DAY * 60

LIVE_STATUSES = ("scheduled", "attended", "no_show")


@dataclass(frozen=True)
class PhysioReportTotals:
    appointments: int
    scheduled: int
    attended: int
    no_show: int
    cancelled: int
    attendance_rate_percent: int
    no_show_rate_percent: int
    cancellation_rate_percent: int


@dataclass(frozen=True)
class PhysioReportOccupancy:
    therapists: int
    available_minutes: int
    booked_minutes: int
    attended_minutes: int
    percent: int


@dataclass(frozen=True)
class PhysioReportRevenue:
    package_cents: int
    single_cents: int
    refunded_cents: int
    net_cents: int
    discount_cents: int
    packages_sold: int
    sessions_sold: int
    single_charges: int


@dataclass(frozen=True)
class PhysioReportPackAdjustments:
    extended: int
    extended_days: int
    voided: int
    voided_sessions: int


@dataclass(frozen=True)
class PhysioReportTherapistRow:
    therapist_employee_id: UUID
    therapist_name: str
    appointments: int
    attended: int
    no_show: int
    attended_minutes: int


@dataclass(frozen=True)
class PhysioReportServiceRow:
    service_id: UUID
    service_name: str
    appointments: int
    attended: int
    no_show: int
    single_charges: int
    single_revenue_cents: int


@dataclass(frozen=True)
class PhysioReportHourRow:
    hour: int
    appointments: int
    attended: int


@dataclass(frozen=True)
class PhysioReportDayRow:
    day: date
    appointments: int
    attended: int
    no_show: int
    cancelled: int
    revenue_cents: int


@dataclass(frozen=True)
class PhysioReport:
    date_from: date
    date_to: date
    totals: PhysioReportTotals
    occupancy: PhysioReportOccupancy
    revenue: PhysioReportRevenue
    adjustments: PhysioReportPackAdjustments
    by_therapist: list[PhysioReportTherapistRow]
    by_service: list[PhysioReportServiceRow]
    by_hour: list[PhysioReportHourRow]
    daily: list[PhysioReportDayRow]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _local_date(value: datetime, period: ReportPeriod) -> date:
    return _as_utc(value).astimezone(period.local_timezone).date()


def _local_hour(value: datetime, period: ReportPeriod) -> int:
    return _as_utc(value).astimezone(period.local_timezone).hour


def _percent(numerator: int, denominator: int) -> int:
    return round(numerator * 100 / denominator) if denominator else 0


def physio_report(session: Session, period: ReportPeriod) -> PhysioReport:
    appointments = session.exec(
        select(PhysioAppointment, PhysioService.name, Employee.first_name, Employee.last_name)
        .join(PhysioService, PhysioService.id == PhysioAppointment.service_id)
        .join(Employee, Employee.id == PhysioAppointment.therapist_employee_id)
        .where(
            PhysioAppointment.starts_at >= period.start_at,
            PhysioAppointment.starts_at < period.end_at,
        )
        .order_by(PhysioAppointment.starts_at)
    ).all()

    counts = {status: 0 for status in ("scheduled", "attended", "no_show", "cancelled")}
    by_therapist: dict[UUID, list] = {}
    by_service: dict[UUID, list] = {}
    by_hour: dict[int, list[int]] = {}
    daily: dict[date, list[int]] = {}
    for day_index in range(period.days):
        daily[period.date_from + timedelta(days=day_index)] = [0, 0, 0, 0, 0]

    for appointment, service_name, first_name, last_name in appointments:
        counts[appointment.status] += 1
        therapist = by_therapist.setdefault(
            appointment.therapist_employee_id,
            [f"{first_name} {last_name}".strip(), 0, 0, 0, 0],
        )
        therapist[1] += 1
        service_row = by_service.setdefault(
            appointment.service_id, [service_name, 0, 0, 0, 0, 0]
        )
        service_row[1] += 1
        hour = _local_hour(appointment.starts_at, period)
        hour_row = by_hour.setdefault(hour, [0, 0])
        hour_row[0] += 1
        day_row = daily[_local_date(appointment.starts_at, period)]
        day_row[0] += 1
        if appointment.status == "attended":
            therapist[2] += 1
            therapist[4] += int(
                (_as_utc(appointment.ends_at) - _as_utc(appointment.starts_at)).total_seconds()
                // 60
            )
            service_row[2] += 1
            hour_row[1] += 1
            day_row[1] += 1
        elif appointment.status == "no_show":
            therapist[3] += 1
            service_row[3] += 1
            day_row[2] += 1
        elif appointment.status == "cancelled":
            day_row[3] += 1

    total_appointments = len(appointments)
    attended = counts["attended"]
    no_show = counts["no_show"]
    finished = attended + no_show
    totals = PhysioReportTotals(
        appointments=total_appointments,
        scheduled=counts["scheduled"],
        attended=attended,
        no_show=no_show,
        cancelled=counts["cancelled"],
        attendance_rate_percent=_percent(attended, finished),
        no_show_rate_percent=_percent(no_show, finished),
        cancellation_rate_percent=_percent(counts["cancelled"], total_appointments),
    )

    booked_minutes = 0
    attended_minutes = 0
    for appointment, *_rest in appointments:
        if appointment.status not in LIVE_STATUSES:
            continue
        minutes = int(
            (_as_utc(appointment.ends_at) - _as_utc(appointment.starts_at)).total_seconds()
            // 60
        )
        booked_minutes += minutes
        if appointment.status == "attended":
            attended_minutes += minutes
    therapists_count = len(by_therapist)
    available_minutes = period.days * ROOM_MINUTES_PER_DAY * therapists_count
    occupancy = PhysioReportOccupancy(
        therapists=therapists_count,
        available_minutes=available_minutes,
        booked_minutes=booked_minutes,
        attended_minutes=attended_minutes,
        percent=_percent(booked_minutes, available_minutes),
    )

    packs = session.exec(
        select(PhysioPack)
        .where(
            PhysioPack.purchased_at >= period.start_at,
            PhysioPack.purchased_at < period.end_at,
        )
    ).all()
    package_cents = sum(pack.price_cents for pack in packs)
    sessions_sold = sum(pack.sessions_total for pack in packs)
    discount_cents = 0
    if packs:
        offer_ids = {pack.offer_id for pack in packs}
        offers = {
            offer.id: offer
            for offer in session.exec(
                select(PhysioOffer).where(PhysioOffer.id.in_(offer_ids))
            ).all()
        }
        discount_cents = sum(
            max(offers[pack.offer_id].list_price_cents - pack.price_cents, 0)
            for pack in packs
            if pack.offer_id in offers
        )

    sales = session.exec(
        select(Sale).where(
            Sale.physio_appointment_id.is_not(None),
            Sale.sold_at >= period.start_at,
            Sale.sold_at < period.end_at,
        )
    ).all()
    single_cents = sum(sale.total_cents for sale in sales)
    for sale in sales:
        day_row = daily.get(_local_date(sale.sold_at, period))
        if day_row is not None:
            day_row[4] += sale.total_cents
    for pack in packs:
        day_row = daily.get(_local_date(pack.purchased_at, period))
        if day_row is not None:
            day_row[4] += pack.price_cents

    physio_sale_ids = {sale.id for sale in sales} | {pack.sale_id for pack in packs}
    returns = (
        session.exec(
            select(SaleReturn).where(
                SaleReturn.sale_id.in_(physio_sale_ids),
                SaleReturn.returned_at >= period.start_at,
                SaleReturn.returned_at < period.end_at,
            )
        ).all()
        if physio_sale_ids
        else []
    )
    refunded_cents = sum(refund.total_refund_cents for refund in returns)
    for refund in returns:
        day_row = daily.get(_local_date(refund.returned_at, period))
        if day_row is not None:
            day_row[4] -= refund.total_refund_cents

    revenue = PhysioReportRevenue(
        package_cents=package_cents,
        single_cents=single_cents,
        refunded_cents=refunded_cents,
        net_cents=package_cents + single_cents - refunded_cents,
        discount_cents=discount_cents,
        packages_sold=len(packs),
        sessions_sold=sessions_sold,
        single_charges=len(sales),
    )

    adjustments = session.exec(
        select(PhysioPackAdjustment).where(
            PhysioPackAdjustment.created_at >= period.start_at,
            PhysioPackAdjustment.created_at < period.end_at,
        )
    ).all()
    extended = [row for row in adjustments if row.kind == "extension"]
    voided = [row for row in adjustments if row.kind == "void"]
    voided_sessions = 0
    if voided:
        changed_packs = session.exec(
            select(PhysioPack).where(
                PhysioPack.id.in_({row.pack_id for row in voided})
            )
        ).all()
        voided_sessions = sum(pack.voided_sessions for pack in changed_packs)
    adjustment_summary = PhysioReportPackAdjustments(
        extended=len(extended),
        extended_days=sum(row.days or 0 for row in extended),
        voided=len(voided),
        voided_sessions=voided_sessions,
    )

    single_by_service: dict[UUID, list[int]] = {}
    for sale in sales:
        appointment = session.get(PhysioAppointment, sale.physio_appointment_id)
        if appointment is None:
            continue
        row = single_by_service.setdefault(appointment.service_id, [0, 0])
        row[0] += 1
        row[1] += sale.total_cents

    return PhysioReport(
        date_from=period.date_from,
        date_to=period.date_to,
        totals=totals,
        occupancy=occupancy,
        revenue=revenue,
        adjustments=adjustment_summary,
        by_therapist=[
            PhysioReportTherapistRow(
                therapist_employee_id=therapist_id,
                therapist_name=values[0],
                appointments=values[1],
                attended=values[2],
                no_show=values[3],
                attended_minutes=values[4],
            )
            for therapist_id, values in sorted(
                by_therapist.items(), key=lambda item: item[1][0]
            )
        ],
        by_service=[
            PhysioReportServiceRow(
                service_id=service_id,
                service_name=values[0],
                appointments=values[1],
                attended=values[2],
                no_show=values[3],
                single_charges=single_by_service.get(service_id, [0, 0])[0],
                single_revenue_cents=single_by_service.get(service_id, [0, 0])[1],
            )
            for service_id, values in sorted(by_service.items(), key=lambda item: item[1][0])
        ],
        by_hour=[
            PhysioReportHourRow(hour=hour, appointments=values[0], attended=values[1])
            for hour, values in sorted(by_hour.items())
        ],
        daily=[
            PhysioReportDayRow(
                day=day,
                appointments=values[0],
                attended=values[1],
                no_show=values[2],
                cancelled=values[3],
                revenue_cents=values[4],
            )
            for day, values in sorted(daily.items())
        ],
    )


def _money(cents: int) -> str:
    return f"{cents / 100:.2f}"


def physio_report_export(report: PhysioReport, period: ReportPeriod) -> ExportTable:
    return ExportTable(
        title=f"Fisioterapia del {period.date_from.isoformat()} al {period.date_to.isoformat()}",
        headers=[
            "Fecha",
            "Citas",
            "Atendidas",
            "Inasistencias",
            "Canceladas",
            "Ingresos (MXN)",
        ],
        rows=[
            [
                row.day.isoformat(),
                str(row.appointments),
                str(row.attended),
                str(row.no_show),
                str(row.cancelled),
                _money(row.revenue_cents),
            ]
            for row in report.daily
        ],
    )
