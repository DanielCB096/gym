"""The member's push switches, one per category of notice.

The inbox keeps every notice; this is only about the phone. A category switched
off stops queueing new pushes and cancels the ones already waiting, so the
member's decision takes effect immediately instead of after the next retry. The
notice itself is still written and still counts as unread: the club's record is
not the member's to silence, only the interruption.

Waiting means two things: a ``pending`` row that no pass has attempted yet, and
a ``failed`` row whose automatic retry is scheduled. The first is deleted (it
never happened); the second is left as history but loses its ``next_attempt_at``,
so the panel still sees the failed attempt while the member stops being rung.

The member can also pick their own silence window, in the club's time zone. It
is not a category switch: nothing is cancelled, the waiting pushes simply do not
leave while that member's clock is inside the window, and the next pass after it
sends them. The club's window still silences everyone, so the two stack.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timezone
from uuid import UUID

from sqlalchemy import delete, update
from sqlmodel import Session, select

from app.modules.memberships.models import Member
from app.modules.notifications.models import (
    MEMBER_NOTIFICATION_CATEGORIES,
    NOTIFICATION_CATEGORY_BY_KIND,
    MemberNotification,
    MemberNotificationPreference,
    MemberNotificationSetting,
    MemberPushDelivery,
    utc_now,
)
from app.timezone import to_club_timezone


class PreferenceError(Exception):
    pass


class UnknownNotificationCategory(PreferenceError):
    pass


class PreferenceMemberNotFound(PreferenceError):
    pass


class PreferenceQuietHoursError(PreferenceError):
    pass


@dataclass(frozen=True)
class MemberNotificationPreferenceItem:
    category: str
    push_enabled: bool
    updated_at: datetime | None


@dataclass(frozen=True)
class MemberQuietHours:
    start: time
    end: time
    updated_at: datetime | None


def category_for_kind(kind: str) -> str:
    """The switch that governs this notice kind.

    The mapping is exhaustive over ``NOTIFICATION_KINDS``; a kind without a
    category is a programming error, not a member-facing one.
    """

    try:
        return NOTIFICATION_CATEGORY_BY_KIND[kind]
    except KeyError:
        raise PreferenceError(
            f"El tipo de aviso '{kind}' no tiene categoría de preferencias"
        ) from None


def _validated_category(category: str) -> str:
    clean = (category or "").strip()
    if clean not in MEMBER_NOTIFICATION_CATEGORIES:
        raise UnknownNotificationCategory(
            f"La categoría de aviso '{category}' no es válida"
        )
    return clean


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def list_member_preferences(
    session: Session, member_id: UUID
) -> list[MemberNotificationPreferenceItem]:
    """Every category in a stable order, with the defaults filled in.

    The app draws one switch per row, so returning the whole set keeps it from
    inventing labels for the categories the member never touched.
    """

    rows = {
        row.category: row
        for row in session.exec(
            select(MemberNotificationPreference).where(
                MemberNotificationPreference.member_id == member_id
            )
        ).all()
    }
    items: list[MemberNotificationPreferenceItem] = []
    for category in MEMBER_NOTIFICATION_CATEGORIES:
        row = rows.get(category)
        items.append(
            MemberNotificationPreferenceItem(
                category=category,
                push_enabled=True if row is None else row.push_enabled,
                updated_at=None if row is None else _as_utc(row.updated_at),
            )
        )
    return items


def update_member_preferences(
    session: Session,
    member_id: UUID,
    changes: Mapping[str, bool],
    *,
    now: datetime | None = None,
) -> list[MemberNotificationPreferenceItem]:
    """Apply the switches the member moved and return the whole set.

    Only the categories present in ``changes`` are touched, so a partial update
    from the app cannot silently reset the others.
    """

    if session.get(Member, member_id) is None:
        raise PreferenceMemberNotFound("El socio no existe")
    occurred = _as_utc(now or utc_now())
    for category, push_enabled in changes.items():
        clean = _validated_category(category)
        row = session.exec(
            select(MemberNotificationPreference).where(
                MemberNotificationPreference.member_id == member_id,
                MemberNotificationPreference.category == clean,
            )
        ).first()
        if row is None:
            row = MemberNotificationPreference(
                member_id=member_id,
                category=clean,
                push_enabled=push_enabled,
                updated_at=occurred,
            )
        else:
            row.push_enabled = push_enabled
            row.updated_at = occurred
        session.add(row)
        if not push_enabled:
            _cancel_waiting_pushes(session, member_id, clean)
    session.commit()
    return list_member_preferences(session, member_id)


def is_push_enabled(session: Session, member_id: UUID, kind: str) -> bool:
    """Whether a notice of this kind should ring the member's phone.

    A member without a row for the category is enabled: silence is something the
    member chooses, never a default.
    """

    category = category_for_kind(kind)
    row = session.exec(
        select(MemberNotificationPreference).where(
            MemberNotificationPreference.member_id == member_id,
            MemberNotificationPreference.category == category,
        )
    ).first()
    return row is None or row.push_enabled


def _parse_quiet_hour(value: str, *, field: str) -> time:
    text = (value or "").strip()
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError as error:
        raise PreferenceQuietHoursError(
            f"La hora de {field} debe tener el formato HH:MM (00:00-23:59); "
            f"recibí {text!r}."
        ) from error


def get_member_quiet_hours(
    session: Session, member_id: UUID
) -> MemberQuietHours | None:
    """The member's own window, or ``None`` when they never set one."""

    row = session.exec(
        select(MemberNotificationSetting).where(
            MemberNotificationSetting.member_id == member_id
        )
    ).first()
    if row is None or row.quiet_start is None or row.quiet_end is None:
        return None
    return MemberQuietHours(
        start=row.quiet_start,
        end=row.quiet_end,
        updated_at=_as_utc(row.updated_at),
    )


def update_member_quiet_hours(
    session: Session,
    member_id: UUID,
    start: str | None,
    end: str | None,
    *,
    now: datetime | None = None,
) -> MemberQuietHours | None:
    """Set or clear the member's own silence window.

    The two hours go together: clearing both removes the row, and sending only
    one is rejected because a half window would look like silence while still
    ringing. Equal hours would silence nothing, so they are rejected too.
    """

    if session.get(Member, member_id) is None:
        raise PreferenceMemberNotFound("El socio no existe")
    only_one = (start is None) != (end is None)
    if only_one:
        raise PreferenceQuietHoursError(
            "La hora de inicio y la de fin se envían juntas: pon las dos o "
            "quita las dos."
        )
    row = session.exec(
        select(MemberNotificationSetting).where(
            MemberNotificationSetting.member_id == member_id
        )
    ).first()
    if start is None or end is None:
        if row is not None:
            session.delete(row)
            session.commit()
        return None
    quiet_start = _parse_quiet_hour(start, field="inicio")
    quiet_end = _parse_quiet_hour(end, field="fin")
    if quiet_start == quiet_end:
        raise PreferenceQuietHoursError(
            "La hora de inicio y la de fin deben ser distintas: con la misma "
            "hora no habría silencio."
        )
    occurred = _as_utc(now or utc_now())
    if row is None:
        row = MemberNotificationSetting(member_id=member_id)
    row.quiet_start = quiet_start
    row.quiet_end = quiet_end
    row.updated_at = occurred
    session.add(row)
    session.commit()
    return get_member_quiet_hours(session, member_id)


def is_quiet_now(quiet: MemberQuietHours, moment: datetime) -> bool:
    """Whether this window silences the member's phone at ``moment``.

    The hours are interpreted in the club's time zone, like the club window, so
    the member and the panel agree on what "22:00" means.
    """

    local = to_club_timezone(_as_utc(moment)).time()
    if quiet.start < quiet.end:
        return quiet.start <= local < quiet.end
    return local >= quiet.start or local < quiet.end


def _cancel_waiting_pushes(
    session: Session, member_id: UUID, category: str
) -> None:
    """Stop the pushes of this category that have not reached a device yet."""

    kinds = tuple(
        kind
        for kind, kind_category in NOTIFICATION_CATEGORY_BY_KIND.items()
        if kind_category == category
    )
    notices = select(MemberNotification.id).where(
        MemberNotification.member_id == member_id,
        MemberNotification.kind.in_(kinds),
    )
    session.exec(
        delete(MemberPushDelivery).where(
            MemberPushDelivery.member_id == member_id,
            MemberPushDelivery.status == "pending",
            MemberPushDelivery.notification_id.in_(notices),
        )
    )
    session.exec(
        update(MemberPushDelivery)
        .where(
            MemberPushDelivery.member_id == member_id,
            MemberPushDelivery.status == "failed",
            MemberPushDelivery.next_attempt_at.is_not(None),
            MemberPushDelivery.notification_id.in_(notices),
        )
        .values(next_attempt_at=None)
    )
