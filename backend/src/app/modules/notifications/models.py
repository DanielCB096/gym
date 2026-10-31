"""Notification inboxes: one for the member, one for the staff.

Two directions of the same conversation live here. The club acts on the member
(a trainer reviews a workout, reception cancels a goal, a spot opens in a class,
the membership is about to expire) and the member's own actions in the app leave
work for the club (a workout waiting to be reviewed, a ticket a technician has
to attend). Until now each side only found that out by opening the screens that
matter to it, so every one of those events appends a short Spanish message to
the inbox of whoever has to act or be informed.

A row is a snapshot of the message, not a pointer to live data, so a
notification keeps making sense after the referenced record is edited or
deleted. ``ref_id`` is an untyped reference used only to deep-link.

Both tables are append-only from the point of view of the reader: the services
create rows through the domain events and the reader can only mark them as read,
never edit or delete them. The staff inbox adds one more state: the service that
emitted an actionable notice can close it with ``resolved_at`` once the work it
announced is done (the trainer reviewed the workout), so the inbox stops
reporting a pending item the panel already attended. The staff inbox is addressed
to an ``app_users`` account because that is what signs in to the panel; the
employee behind that account is what a trainer-owned assignment or a ticket
points at, so the audience is resolved employee → account when the notice is
emitted.
"""

from datetime import datetime, time, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


NOTIFICATION_KINDS = (
    "workout_reviewed",
    "goal_achieved",
    "goal_cancelled_by_staff",
    "goal_updated_by_staff",
    "class_waitlist_promoted",
    "membership_expiring",
    "equipment_out_of_service",
    "invoice_stamped",
    "invoice_failed",
    "invoice_cancelled",
    "class_reminder",
    "class_reserved",
    "class_cancelled",
    "class_rescheduled",
    "physio_appointment_scheduled",
    "physio_appointment_cancelled",
    "physio_appointment_rescheduled",
    "physio_reminder",
)
MAX_TITLE_CHARS = 140
MAX_BODY_CHARS = 500
MAX_DEDUPE_CHARS = 120
MAX_MESSAGE_ID_CHARS = 320

# The app groups the notice kinds into the few switches a person can tell apart.
# Every kind belongs to exactly one category; a test asserts the mapping is
# exhaustive, so a new kind cannot ship without deciding what silences it.
MEMBER_NOTIFICATION_CATEGORIES = (
    "membership",
    "classes",
    "training",
    "billing",
    "equipment",
    "physio",
)

NOTIFICATION_CATEGORY_BY_KIND = {
    "membership_expiring": "membership",
    "class_waitlist_promoted": "classes",
    "class_reserved": "classes",
    "class_cancelled": "classes",
    "class_rescheduled": "classes",
    "class_reminder": "classes",
    "workout_reviewed": "training",
    "goal_achieved": "training",
    "goal_cancelled_by_staff": "training",
    "goal_updated_by_staff": "training",
    "invoice_stamped": "billing",
    "invoice_failed": "billing",
    "invoice_cancelled": "billing",
    "equipment_out_of_service": "equipment",
    "physio_appointment_scheduled": "physio",
    "physio_appointment_cancelled": "physio",
    "physio_appointment_rescheduled": "physio",
    "physio_reminder": "physio",
}


class MemberNotification(SQLModel, table=True):
    __tablename__ = "member_notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('workout_reviewed', 'goal_achieved', 'goal_cancelled_by_staff', "
            "'goal_updated_by_staff', 'class_waitlist_promoted', 'membership_expiring', "
            "'equipment_out_of_service', 'invoice_stamped', 'invoice_failed', "
            "'invoice_cancelled', 'class_reminder', 'class_reserved', "
            "'class_cancelled', 'class_rescheduled', 'physio_appointment_scheduled', "
            "'physio_appointment_cancelled', 'physio_appointment_rescheduled', "
            "'physio_reminder')",
            name="ck_member_notifications_kind",
        ),
        CheckConstraint(
            f"length(title) BETWEEN 1 AND {MAX_TITLE_CHARS}",
            name="ck_member_notifications_title_length",
        ),
        CheckConstraint(
            f"length(body) BETWEEN 1 AND {MAX_BODY_CHARS}",
            name="ck_member_notifications_body_length",
        ),
        Index("ix_member_notifications_member_time", "member_id", "created_at"),
        Index("ix_member_notifications_member_unread", "member_id", "read_at"),
        Index(
            "ix_member_notifications_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
            sqlite_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)
    )
    kind: str = Field(max_length=40)
    title: str = Field(max_length=MAX_TITLE_CHARS)
    body: str = Field(sa_column=Column(String(length=MAX_BODY_CHARS), nullable=False))
    ref_id: UUID | None = Field(default=None, sa_column=Column(Uuid(as_uuid=True)))
    dedupe_key: str | None = Field(
        default=None, sa_column=Column(String(length=MAX_DEDUPE_CHARS))
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class MemberNotificationPreference(SQLModel, table=True):
    """One push switch of one member for one category of notice.

    Only the phone is switched, never the inbox: the notice is still written and
    still counts as unread, because the member did not ask to miss it, only to be
    interrupted less. A missing row means enabled, so the table only stores the
    decisions the member actually made and a new category starts on by default.
    The row is kept (rather than deleted) when the switch goes back on, so the
    panel can tell an explicit "on" from a member who never touched the switch.
    """

    __tablename__ = "member_notification_preferences"
    __table_args__ = (
        CheckConstraint(
            "category IN ('membership', 'classes', 'training', 'billing', "
            "'equipment', 'physio')",
            name="ck_member_notification_preferences_category",
        ),
        UniqueConstraint(
            "member_id",
            "category",
            name="uq_member_notification_preferences_member_category",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    category: str = Field(max_length=24)
    push_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class MemberNotificationSetting(SQLModel, table=True):
    """The member's own silence window for pushes, one row per member.

    The club's window (``MEMBER_PUSH_QUIET_START``/``_END``) silences everyone
    at once; this is the member's own, in the club's time zone, and only holds
    back the phone: the notice is still written and counted. Both hours live in
    the same row and go together — a half-configured window is rejected by the
    CHECK — and an equal pair would silence nothing, so it is rejected too.
    A member without a row has no personal window.
    """

    __tablename__ = "member_notification_settings"
    __table_args__ = (
        CheckConstraint(
            "(quiet_start IS NULL AND quiet_end IS NULL) OR "
            "(quiet_start IS NOT NULL AND quiet_end IS NOT NULL "
            "AND quiet_start <> quiet_end)",
            name="ck_member_notification_settings_quiet_pair",
        ),
        UniqueConstraint(
            "member_id",
            name="uq_member_notification_settings_member",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    quiet_start: time | None = Field(
        default=None, sa_column=Column(Time(), nullable=True)
    )
    quiet_end: time | None = Field(
        default=None, sa_column=Column(Time(), nullable=True)
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


STAFF_NOTIFICATION_KINDS = (
    "workout_pending_review",
    "maintenance_ticket_assigned",
    "kiosk_token_expiring",
    "attendance_corrected",
    "attendance_voided",
    "attendance_request_pending",
    "attendance_request_approved",
    "attendance_request_rejected",
    "attendance_request_overdue",
    "member_push_failed",
    "member_push_receipt_failed",
)

# Every staff notice now leaves the panel: the bell keeps the history, the email
# reaches the account that owns the work. The tuple stays explicit so a future
# kind has to opt in instead of mailing itself by default.
STAFF_NOTIFICATION_EMAIL_KINDS = STAFF_NOTIFICATION_KINDS


class StaffNotification(SQLModel, table=True):
    """An inbox row addressed to a panel account instead of to a member."""

    __tablename__ = "staff_notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('workout_pending_review', 'maintenance_ticket_assigned', "
            "'kiosk_token_expiring', 'attendance_corrected', 'attendance_voided', "
            "'attendance_request_pending', 'attendance_request_approved', "
            "'attendance_request_rejected', 'attendance_request_overdue', "
            "'member_push_failed', 'member_push_receipt_failed')",
            name="ck_staff_notifications_kind",
        ),
        CheckConstraint(
            f"length(title) BETWEEN 1 AND {MAX_TITLE_CHARS}",
            name="ck_staff_notifications_title_length",
        ),
        CheckConstraint(
            f"length(body) BETWEEN 1 AND {MAX_BODY_CHARS}",
            name="ck_staff_notifications_body_length",
        ),
        Index("ix_staff_notifications_user_time", "user_id", "created_at"),
        Index("ix_staff_notifications_user_unread", "user_id", "read_at"),
        Index(
            "ix_staff_notifications_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
            sqlite_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    )
    kind: str = Field(max_length=40)
    title: str = Field(max_length=MAX_TITLE_CHARS)
    body: str = Field(sa_column=Column(String(length=MAX_BODY_CHARS), nullable=False))
    ref_id: UUID | None = Field(default=None, sa_column=Column(Uuid(as_uuid=True)))
    dedupe_key: str | None = Field(
        default=None, sa_column=Column(String(length=MAX_DEDUPE_CHARS))
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    resolved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class StaffNotificationDelivery(SQLModel, table=True):
    """An email queued for one staff notice.

    The row is written in the same transaction as the notice, so a rolled-back
    change never leaves a message to send and a committed one cannot be
    forgotten. ``pending`` means the SMTP server was not contacted yet; the
    following attempt records ``sent``, ``simulated`` (preview mode) or
    ``failed`` with the transport error. ``recipient`` is a snapshot of the
    account's address at the time of the notice, because the account may be
    edited later. ``message_id`` is the identifier the message left with, so a
    provider's acknowledgement can be matched back to this row.
    """

    __tablename__ = "staff_notification_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'simulated', 'failed')",
            name="ck_staff_notification_deliveries_status",
        ),
        CheckConstraint(
            "attempts >= 0", name="ck_staff_notification_deliveries_attempts"
        ),
        UniqueConstraint(
            "notice_id", name="uq_staff_notification_deliveries_notice"
        ),
        Index(
            "ix_staff_notification_deliveries_status_created",
            "status",
            "created_at",
        ),
        Index(
            "ix_staff_notification_deliveries_message_id",
            "message_id",
            unique=True,
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    notice_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("staff_notifications.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    recipient: str = Field(max_length=254)
    message_id: str | None = Field(default=None, max_length=MAX_MESSAGE_ID_CHARS)
    status: str = Field(
        default="pending",
        sa_column=Column(String(16), nullable=False, server_default=text("'pending'")),
    )
    attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    error: str | None = Field(default=None, max_length=500)
    last_attempt_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    sent_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


RECEIPT_EVENT_TYPES = ("delivered", "bounced", "complained")
MAX_PROVIDER_EVENT_CHARS = 120


class StaffNotificationDeliveryReceipt(SQLModel, table=True):
    """What the mail provider said about a message that already left.

    The delivery row records the SMTP answer; it cannot know what happened
    afterwards. A provider reports that later —the mailbox accepted the message,
    the address bounced, the recipient marked it as spam— and each report is
    appended here instead of overwriting the transport status, so ``sent`` keeps
    meaning "the server accepted it" while the receipt tells whether it arrived.
    ``provider_event_id`` is unique for the whole table: the provider retries its
    webhook until it gets a 2xx, and the same event must never be stored twice.
    """

    __tablename__ = "staff_notification_delivery_receipts"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('delivered', 'bounced', 'complained')",
            name="ck_staff_notification_delivery_receipts_event",
        ),
        UniqueConstraint(
            "provider_event_id",
            name="uq_staff_notification_delivery_receipts_event",
        ),
        Index(
            "ix_staff_notification_delivery_receipts_delivery_time",
            "delivery_id",
            "received_at",
        ),
        Index(
            "ix_staff_notification_delivery_receipts_received",
            "received_at",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    delivery_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("staff_notification_deliveries.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    provider_event_id: str = Field(max_length=MAX_PROVIDER_EVENT_CHARS)
    event_type: str = Field(max_length=16)
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    detail: str | None = Field(default=None, max_length=500)
    received_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


PUSH_PLATFORMS = ("ios", "android")
MAX_PUSH_TOKEN_CHARS = 255
MAX_EXPO_TICKET_CHARS = 100
# Expo answers a send with a ticket and the ticket's receipt later says whether
# the device got it. ``expired`` records a receipt Expo no longer keeps (24 h).
PUSH_RECEIPT_STATUSES = ("ok", "error", "expired")


class MemberPushToken(SQLModel, table=True):
    """A device where the member's app can receive notifications.

    The token is issued by Expo per installation, so the same person may have
    several active tokens (phone and tablet) and the same token may be handed to
    another member when the device changes accounts: registration transfers the
    token instead of duplicating it. Deactivation is a flag, not a delete, so the
    delivery history keeps pointing at the device it was sent to.
    """

    __tablename__ = "member_push_tokens"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('ios', 'android')",
            name="ck_member_push_tokens_platform",
        ),
        UniqueConstraint("token", name="uq_member_push_tokens_token"),
        Index("ix_member_push_tokens_member_active", "member_id", "active"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    token: str = Field(max_length=MAX_PUSH_TOKEN_CHARS)
    platform: str = Field(max_length=8)
    active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_seen_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    deactivated_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )


class MemberPushDelivery(SQLModel, table=True):
    """One push queued for one notification and one device.

    Written in the same transaction as the notice, one row per active token, so
    a rolled-back change never leaves a push behind. ``token`` is a snapshot: the
    device may be retired before the pass runs and the row must still say where
    the attempt went. ``status`` follows the same four values as the email queue,
    and the unique pair keeps a replayed notice from queueing twice.
    ``next_attempt_at`` is the automatic retry the next pass will pick up; it is
    ``NULL`` while there is nothing scheduled, either because the push left or
    because the attempts ran out.
    """

    __tablename__ = "member_push_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'simulated', 'failed')",
            name="ck_member_push_deliveries_status",
        ),
        CheckConstraint(
            "attempts >= 0", name="ck_member_push_deliveries_attempts"
        ),
        UniqueConstraint(
            "notification_id",
            "token",
            name="uq_member_push_deliveries_notification_token",
        ),
        Index(
            "ix_member_push_deliveries_status_created",
            "status",
            "created_at",
        ),
        Index(
            "ix_member_push_deliveries_status_next",
            "status",
            "next_attempt_at",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    notification_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("member_notifications.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    member_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    token: str = Field(max_length=MAX_PUSH_TOKEN_CHARS)
    status: str = Field(
        default="pending",
        sa_column=Column(String(16), nullable=False, server_default=text("'pending'")),
    )
    attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    error: str | None = Field(default=None, max_length=500)
    last_attempt_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    next_attempt_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    sent_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    # Expo's ticket for the accepted send; it is what the receipts pass asks
    # about later. ``receipt_checked_at`` throttles that question while Expo has
    # no answer yet, so a pass does not repeat the same lookup every minute.
    expo_ticket_id: str | None = Field(
        default=None, max_length=MAX_EXPO_TICKET_CHARS
    )
    receipt_checked_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class MemberPushDeliveryReceipt(SQLModel, table=True):
    """What Expo said about a push after accepting it.

    ``sent`` means Expo took the message; only the ticket's receipt says whether
    the phone got it. One row per delivery: the ticket identifies the send, so a
    second receipt for the same ticket is the same answer and never a new row.
    The delivery's status is not rewritten — the receipt is information beside
    the queue, exactly like the staff email receipts of ADR-051.
    """

    __tablename__ = "member_push_delivery_receipts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok', 'error', 'expired')",
            name="ck_member_push_delivery_receipts_status",
        ),
        UniqueConstraint("delivery_id", name="uq_member_push_delivery_receipts_delivery"),
        UniqueConstraint("ticket_id", name="uq_member_push_delivery_receipts_ticket"),
        Index(
            "ix_member_push_delivery_receipts_received",
            "received_at",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    delivery_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("member_push_deliveries.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    ticket_id: str = Field(max_length=MAX_EXPO_TICKET_CHARS)
    status: str = Field(max_length=16)
    detail: str | None = Field(default=None, max_length=500)
    received_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )

MAX_PUSH_ENDPOINT_CHARS = 500
MAX_PUSH_KEY_CHARS = 200
# Web Push speaks to the panel's browser, not to the member app: one row per
# browser profile that opted in.
STAFF_PUSH_DELIVERY_STATUSES = ("pending", "sent", "simulated", "failed")


class StaffPushSubscription(SQLModel, table=True):
    """A browser where a panel account opted in to receive pushes.

    The endpoint is the capability URL the push service issued for that
    installation; it is unique because a browser profile has exactly one live
    subscription per push service, and registering it again from another account
    transfers it instead of leaving the previous one receiving the new one's
    notices. Deactivation is a flag, not a delete, so the delivery history keeps
    pointing at the device it was sent to. The encryption keys travel with the
    subscription (``p256dh`` and ``auth``), which is why the panel never needs to
    send them again after registering.
    """

    __tablename__ = "staff_push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_staff_push_subscriptions_endpoint"),
        Index("ix_staff_push_subscriptions_user_active", "user_id", "active"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    endpoint: str = Field(max_length=MAX_PUSH_ENDPOINT_CHARS)
    p256dh: str = Field(max_length=MAX_PUSH_KEY_CHARS)
    auth: str = Field(max_length=MAX_PUSH_KEY_CHARS)
    user_agent: str | None = Field(default=None, max_length=255)
    active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_seen_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    deactivated_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )


class StaffPushDelivery(SQLModel, table=True):
    """One push queued for one staff notice and one browser.

    Written in the same transaction as the notice, one row per active
    subscription, so a rolled-back change never leaves a push behind and a
    deduplicated replay never queues twice. ``endpoint`` is a snapshot: the
    subscription may be retired before the pass runs and the row must still say
    where the attempt went. There is no automatic retry: a failed row waits for
    the operator, because a broken push channel must not keep ringing every
    panel account that receives the resulting alerts.
    """

    __tablename__ = "staff_push_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'simulated', 'failed')",
            name="ck_staff_push_deliveries_status",
        ),
        CheckConstraint(
            "attempts >= 0", name="ck_staff_push_deliveries_attempts"
        ),
        UniqueConstraint(
            "notice_id",
            "subscription_id",
            name="uq_staff_push_deliveries_notice_subscription",
        ),
        Index(
            "ix_staff_push_deliveries_status_created",
            "status",
            "created_at",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    notice_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("staff_notifications.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    user_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    subscription_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("staff_push_subscriptions.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    endpoint: str = Field(max_length=MAX_PUSH_ENDPOINT_CHARS)
    status: str = Field(
        default="pending",
        sa_column=Column(String(16), nullable=False, server_default=text("'pending'")),
    )
    attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    error: str | None = Field(default=None, max_length=500)
    last_attempt_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    sent_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
