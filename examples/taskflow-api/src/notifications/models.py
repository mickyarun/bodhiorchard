"""Notification models — in-app and email notification records."""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
import enum

from src.shared.database import Base


class NotificationType(str, enum.Enum):
    TASK_ASSIGNED = "task_assigned"
    TASK_COMMENT = "task_comment"
    TASK_STATUS_CHANGED = "task_status_changed"
    INVOICE_READY = "invoice_ready"
    REMINDER = "reminder"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String, nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text)
    is_read = Column(Boolean, default=False)
    link = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    email_enabled = Column(Boolean, default=True)
    push_enabled = Column(Boolean, default=True)
    digest_frequency = Column(String, default="daily")  # daily, weekly, none
