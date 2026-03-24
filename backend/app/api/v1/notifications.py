"""Notification REST endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.notification import NotificationRepository
from app.schemas.notification import NotificationRead

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["notifications"])


def _repo(db: AsyncSession, user: User) -> NotificationRepository:
    """Build a user-scoped notification repository."""
    return NotificationRepository(db, user_id=user.id)


@router.get("/", response_model=list[NotificationRead])
async def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationRead]:
    """List active (non-dismissed) notifications for the current user."""
    repo = _repo(db, current_user)
    items = await repo.list_active(limit=limit, offset=offset)
    return [NotificationRead.model_validate(n) for n in items]


@router.get("/unread-count")
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Return unread notification count for badge display."""
    repo = _repo(db, current_user)
    count = await repo.unread_count()
    return {"count": count}


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRead:
    """Mark a single notification as read."""
    repo = _repo(db, current_user)
    notif = await repo.mark_read(notification_id)
    if notif is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return NotificationRead.model_validate(notif)


@router.post("/read-all")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Mark all unread notifications as read."""
    repo = _repo(db, current_user)
    count = await repo.mark_all_read()
    return {"updated": count}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Dismiss (soft-delete) a single notification."""
    repo = _repo(db, current_user)
    found = await repo.dismiss(notification_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Dismiss all active notifications."""
    repo = _repo(db, current_user)
    await repo.dismiss_all()
