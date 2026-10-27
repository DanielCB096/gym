"""Member notification inbox module."""

from app.modules.notifications.models import (
    MAX_BODY_CHARS,
    MAX_TITLE_CHARS,
    NOTIFICATION_KINDS,
    MemberNotification,
)
from app.modules.notifications.service import (
    MemberNotificationItem,
    MemberNotificationPage,
    NotificationError,
    NotificationNotFound,
    create_notification,
    list_member_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    notify_goal_achieved,
    notify_goal_cancelled_by_staff,
    notify_goal_updated_by_staff,
    notify_waitlist_promoted,
    notify_workout_reviewed,
    unread_notification_count,
)

__all__ = [
    "MAX_BODY_CHARS",
    "MAX_TITLE_CHARS",
    "NOTIFICATION_KINDS",
    "MemberNotification",
    "MemberNotificationItem",
    "MemberNotificationPage",
    "NotificationError",
    "NotificationNotFound",
    "create_notification",
    "list_member_notifications",
    "mark_all_notifications_read",
    "mark_notification_read",
    "notify_goal_achieved",
    "notify_goal_cancelled_by_staff",
    "notify_goal_updated_by_staff",
    "notify_waitlist_promoted",
    "notify_workout_reviewed",
    "unread_notification_count",
]
