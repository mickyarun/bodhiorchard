"""Notification service — create, read, mark-read, dispatch to queue."""

from sqlalchemy.orm import Session

from src.notifications.models import Notification, NotificationPreference, NotificationType


def create_notification(
    db: Session,
    user_id: int,
    notif_type: NotificationType,
    title: str,
    body: str = "",
    link: str | None = None,
) -> Notification:
    """Create an in-app notification and queue it for email/push delivery."""
    notif = Notification(
        user_id=user_id,
        type=notif_type.value,
        title=title,
        body=body,
        link=link,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # Check preferences and dispatch to worker queue
    prefs = get_preferences(db, user_id)
    if prefs and prefs.email_enabled:
        _enqueue_email(user_id, title, body)
    if prefs and prefs.push_enabled:
        _enqueue_push(user_id, title, body)

    return notif


def list_notifications(db: Session, user_id: int, unread_only: bool = False) -> list[Notification]:
    """Get notifications for a user."""
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc()).limit(50).all()


def mark_read(db: Session, notification_id: int, user_id: int) -> bool:
    """Mark a notification as read."""
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not notif:
        return False
    notif.is_read = True
    db.commit()
    return True


def mark_all_read(db: Session, user_id: int) -> int:
    """Mark all notifications as read for a user."""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .update({"is_read": True})
    )
    db.commit()
    return count


def get_preferences(db: Session, user_id: int) -> NotificationPreference | None:
    """Get notification preferences for a user."""
    return db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).first()


def update_preferences(
    db: Session, user_id: int, email_enabled: bool, push_enabled: bool, digest_frequency: str
) -> NotificationPreference:
    """Create or update notification preferences."""
    prefs = get_preferences(db, user_id)
    if not prefs:
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
    prefs.email_enabled = email_enabled
    prefs.push_enabled = push_enabled
    prefs.digest_frequency = digest_frequency
    db.commit()
    db.refresh(prefs)
    return prefs


def _enqueue_email(user_id: int, title: str, body: str) -> None:
    """Queue an email notification for the background worker."""
    # In production, this would publish to Redis/RabbitMQ
    # The taskflow-worker picks up these messages
    pass


def _enqueue_push(user_id: int, title: str, body: str) -> None:
    """Queue a push notification for the background worker."""
    pass
