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

"""Notification creation and delivery service.

Extracted from job_queue.py for reusability and testability.
Handles deep-link construction, DB persistence, and WS delivery.
"""

import asyncio
import datetime as _dt
import re
import uuid
from typing import Any

import structlog

from app.schemas.bud import SECTION_TO_TAB
from app.schemas.jobs import JobState, JobStatusRead

logger = structlog.get_logger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

_JOB_LABELS: dict[str, str] = {
    "bud_chat": "BUD Chat",
    "bud_agent": "BUD Agent",
    "design_agent": "Design Agent",
    "design_extract": "Design System Extraction",
    "prd_agent": "PRD Agent",
    "tech_arch": "Tech Architecture",
}

_ALLOWED_DEEP_LINK_PREFIXES = ("/buds/", "/settings/")


def build_deep_link(job_type: str, payload: dict[str, Any]) -> str | None:
    """Build a validated deep-link from job type and payload.

    Returns None if job type is unknown or payload lacks required fields.
    """
    if job_type == "design_extract":
        return "/settings/design-systems"

    bud_id = payload.get("bud_id", "")
    if not isinstance(bud_id, str) or not _UUID_RE.match(bud_id):
        return None

    base = f"/buds/{bud_id}"

    if job_type == "bud_chat":
        section = payload.get("section", "")
        tab = SECTION_TO_TAB.get(section)
        if tab:
            return f"{base}?tab={tab}"
        return base

    if job_type == "design_agent":
        return f"{base}?tab=design"

    if job_type == "prd_agent":
        return f"{base}?tab=requirements"

    if job_type == "tech_arch":
        return f"{base}?tab=tech-spec"

    return None


def send_job_notification(
    job: JobStatusRead,
    *,
    user_id: str,
    org_id: str,
    payload: dict[str, Any],
) -> None:
    """Create a DB notification and push via WS for a completed/failed job.

    Fire-and-forget: persists to DB first (durable), then publishes WS.
    Accepts org_id explicitly (not from payload) so callers pass the
    authenticated user's org, not untrusted payload data.

    Must be called from an async context (i.e. within a running event loop).
    This is always the case when called from job queue workers.
    """
    label = _JOB_LABELS.get(job.job_type)
    if label is None:
        return

    if not org_id:
        logger.warning(
            "notification_skipped_no_org_id",
            job_id=job.job_id,
            job_type=job.job_type,
        )
        return

    deep_link = build_deep_link(job.job_type, payload)

    # Validate deep link against allowlist
    if deep_link and not any(deep_link.startswith(p) for p in _ALLOWED_DEEP_LINK_PREFIXES):
        deep_link = None

    failed = job.state == JobState.FAILED
    notif_type = "job_failed" if failed else "job_completed"
    title = f"{label} {'failed' if failed else 'completed'}"
    message = job.error[:500] if failed and job.error else (job.status_message or "")

    notif_id = uuid.uuid4()

    async def _persist_and_publish() -> None:
        from app.database import AsyncSessionLocal
        from app.models.notification import Notification, NotificationType
        from app.services.event_bus import publish

        persisted = False
        try:
            async with AsyncSessionLocal() as db:
                notif = Notification(
                    id=notif_id,
                    org_id=uuid.UUID(org_id),
                    user_id=uuid.UUID(user_id),
                    type=NotificationType(notif_type),
                    title=title,
                    message=message,
                    deep_link=deep_link,
                    job_id=job.job_id,
                    job_type=job.job_type,
                )
                db.add(notif)
                await db.commit()
                persisted = True
        except Exception:
            logger.exception(
                "notification_persist_failed",
                job_id=job.job_id,
                user_id=user_id,
            )

        try:
            ws_payload = {
                "id": str(notif_id) if persisted else None,
                "type": notif_type,
                "jobId": job.job_id,
                "jobType": job.job_type,
                "title": title,
                "message": message,
                "deepLink": deep_link,
                "isRead": False,
                "isDismissed": False,
                "createdAt": _dt.datetime.now(_dt.UTC).isoformat(),
            }
            publish(f"notifications:{user_id}", ws_payload)
        except Exception:
            logger.exception(
                "notification_ws_publish_failed",
                job_id=job.job_id,
                user_id=user_id,
            )

    asyncio.get_running_loop().create_task(_persist_and_publish())


def send_scan_notification(
    *,
    scan_id: str,
    user_id: str,
    org_id: str,
    completed: bool,
    features_indexed: int = 0,
    profiles_found: int = 0,
    error_message: str | None = None,
) -> None:
    """Send push notification for scan completion or failure.

    Reuses ``job_completed``/``job_failed`` notification types since the
    frontend icon logic works identically for scans.

    Args:
        scan_id: The scan identifier.
        user_id: User who triggered the scan.
        org_id: Organization UUID string.
        completed: True if scan succeeded, False if failed.
        features_indexed: Number of features found (success only).
        profiles_found: Number of skill profiles found (success only).
        error_message: Error description (failure only).
    """
    if not org_id:
        logger.warning("scan_notification_skipped_no_org_id", scan_id=scan_id)
        return

    notif_type = "job_completed" if completed else "job_failed"
    title = "Repository Scan completed" if completed else "Repository Scan failed"

    if completed:
        message = f"{features_indexed} features indexed, {profiles_found} skill profiles found."
    else:
        message = (error_message or "Scan failed")[:500]

    deep_link = "/settings"
    notif_id = uuid.uuid4()

    async def _persist_and_publish() -> None:
        from app.database import AsyncSessionLocal
        from app.models.notification import Notification, NotificationType
        from app.services.event_bus import publish

        persisted = False
        try:
            async with AsyncSessionLocal() as db:
                notif = Notification(
                    id=notif_id,
                    org_id=uuid.UUID(org_id),
                    user_id=uuid.UUID(user_id),
                    type=NotificationType(notif_type),
                    title=title,
                    message=message,
                    deep_link=deep_link,
                    job_id=scan_id,
                    job_type="scan",
                )
                db.add(notif)
                await db.commit()
                persisted = True
        except Exception:
            logger.exception(
                "scan_notification_persist_failed",
                scan_id=scan_id,
                user_id=user_id,
            )

        try:
            ws_payload = {
                "id": str(notif_id) if persisted else None,
                "type": notif_type,
                "jobId": scan_id,
                "jobType": "scan",
                "title": title,
                "message": message,
                "deepLink": deep_link,
                "isRead": False,
                "isDismissed": False,
                "createdAt": _dt.datetime.now(_dt.UTC).isoformat(),
            }
            publish(f"notifications:{user_id}", ws_payload)
        except Exception:
            logger.exception(
                "scan_notification_ws_failed",
                scan_id=scan_id,
                user_id=user_id,
            )

    asyncio.get_running_loop().create_task(_persist_and_publish())


def send_lifecycle_notification(
    *,
    org_id: str,
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    bud_id: str | None = None,
) -> None:
    """Send a lifecycle notification (approval, assignment, reassignment).

    Fire-and-forget: persists to DB, then publishes via WS.
    Must be called from an async context.
    """
    if not org_id or not user_id:
        return

    deep_link = f"/buds/{bud_id}" if bud_id and _UUID_RE.match(bud_id) else None

    # Validate deep link against allowlist
    if deep_link and not any(deep_link.startswith(p) for p in _ALLOWED_DEEP_LINK_PREFIXES):
        deep_link = None

    notif_id = uuid.uuid4()

    async def _persist_and_publish() -> None:
        from app.database import AsyncSessionLocal
        from app.models.notification import Notification, NotificationType
        from app.services.event_bus import publish

        persisted = False
        try:
            async with AsyncSessionLocal() as db:
                notif = Notification(
                    id=notif_id,
                    org_id=uuid.UUID(org_id),
                    user_id=uuid.UUID(user_id),
                    type=NotificationType(notification_type),
                    title=title,
                    message=message,
                    deep_link=deep_link,
                )
                db.add(notif)
                await db.commit()
                persisted = True
        except Exception:
            logger.exception(
                "lifecycle_notification_persist_failed",
                user_id=user_id,
                notification_type=notification_type,
            )

        try:
            ws_payload = {
                "id": str(notif_id) if persisted else None,
                "type": notification_type,
                "jobId": None,
                "jobType": None,
                "title": title,
                "message": message,
                "deepLink": deep_link,
                "isRead": False,
                "isDismissed": False,
                "createdAt": _dt.datetime.now(_dt.UTC).isoformat(),
            }
            publish(f"notifications:{user_id}", ws_payload)
        except Exception:
            logger.exception(
                "lifecycle_notification_ws_failed",
                user_id=user_id,
                notification_type=notification_type,
            )

    asyncio.get_running_loop().create_task(_persist_and_publish())
