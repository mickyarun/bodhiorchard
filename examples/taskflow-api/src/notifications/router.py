"""Notification API endpoints — list, mark read, preferences."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.shared.database import get_db
from src.auth.permissions import get_current_user
from src.notifications.service import (
    list_notifications,
    mark_read,
    mark_all_read,
    delete_notification,
    update_preferences,
)

router = APIRouter()


class PreferencesRequest(BaseModel):
    email_enabled: bool = True
    push_enabled: bool = True
    digest_frequency: str = "daily"


@router.get("")
def index(unread_only: bool = False, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """List notifications for the current user."""
    notifs = list_notifications(db, user["user_id"], unread_only=unread_only)
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "is_read": n.is_read,
            "link": n.link,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifs
    ]


@router.patch("/{notification_id}/read")
def read(notification_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark a single notification as read."""
    mark_read(db, notification_id, user["user_id"])
    return {"detail": "Marked as read"}


@router.post("/read-all")
def read_all(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark all notifications as read."""
    count = mark_all_read(db, user["user_id"])
    return {"marked": count}


@router.delete("/{notification_id}", status_code=204)
def delete(notification_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete a single notification."""
    found = delete_notification(db, notification_id, user["user_id"])
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")


@router.put("/preferences")
def set_preferences(body: PreferencesRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update notification preferences."""
    prefs = update_preferences(db, user["user_id"], body.email_enabled, body.push_enabled, body.digest_frequency)
    return {"email_enabled": prefs.email_enabled, "push_enabled": prefs.push_enabled}
