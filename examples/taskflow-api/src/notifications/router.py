# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Notification API endpoints — list, mark read, preferences."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.shared.database import get_db
from src.auth.permissions import get_current_user
from src.notifications.service import (
    list_notifications,
    mark_read,
    mark_all_read,
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
    return [{"id": n.id, "type": n.type, "title": n.title, "is_read": n.is_read} for n in notifs]


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


@router.put("/preferences")
def set_preferences(body: PreferencesRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update notification preferences."""
    prefs = update_preferences(db, user["user_id"], body.email_enabled, body.push_enabled, body.digest_frequency)
    return {"email_enabled": prefs.email_enabled, "push_enabled": prefs.push_enabled}
