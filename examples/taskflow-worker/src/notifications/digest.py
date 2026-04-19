"""Notification digest — aggregates unread notifications into a summary email.

Runs on a schedule (daily or weekly per user preference) and sends
a single digest email instead of individual notifications.
"""


def build_digest(user_id: int, period: str = "daily") -> dict:
    """Collect unread notifications for a user and format a digest.

    Args:
        user_id: The user to build digest for.
        period: "daily" or "weekly".

    Returns:
        Dict with subject, body, and notification count.
    """
    # In production: query notifications from DB
    return {
        "subject": f"Your {period} TaskFlow digest",
        "body": "You have 5 unread notifications...",
        "count": 5,
    }


def handle_digest_job(payload: dict) -> None:
    """Process a digest notification job."""
    user_id = payload["user_id"]
    period = payload.get("period", "daily")

    digest = build_digest(user_id, period)
    if digest["count"] == 0:
        return  # Nothing to send

    from src.notifications.email_sender import send_email

    send_email(
        to_email=payload["email"],
        subject=digest["subject"],
        body=digest["body"],
    )
