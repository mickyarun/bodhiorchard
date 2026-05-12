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

"""Jira import API endpoints.

Provides connection management, project discovery, import triggering,
and session history for the Jira import pipeline.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.jira_import import ImportStatus, JiraImportSession, JiraIssueBudMap
from app.models.user import User
from app.repositories.jira_import import (
    JiraImportSessionRepository,
    JiraIssueBudMapRepository,
)
from app.schemas.jira_import import (
    JiraConnectionStatus,
    JiraConnectRequest,
    JiraDiscoverRequest,
    JiraDiscoveryPayload,
    JiraImportPayload,
    JiraImportRequest,
    JiraImportSessionList,
    JiraImportSessionRead,
)
from app.schemas.settings import JiraSettings
from app.services.jira_client import JiraClient

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["jira"])


# ── Connection ────────────────────────────────────────────────────


@router.post(
    "/connect",
    response_model=JiraConnectionStatus,
    dependencies=[Depends(require_permissions("integrations:configure"))],
)
async def connect_jira(
    body: JiraConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JiraConnectionStatus:
    """Save Jira credentials and test the connection."""
    from app.services.jira_client import JiraApiError, JiraClient

    client = JiraClient(site_url=body.site_url, email=body.email, api_token=body.api_token)

    try:
        info = await client.test_connection()
    except JiraApiError as exc:
        return JiraConnectionStatus(connected=False, error=str(exc))

    site_id = info.get("baseUrl", body.site_url)

    # Persist to org.config.jira
    from app.models.organization import Organization

    org = await db.get(Organization, current_user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    from app.core.encryption import encrypt_secret

    config = dict(org.config or {})
    config["jira"] = {
        "site_id": site_id,
        "site_url": body.site_url.rstrip("/"),
        "email": body.email,
        "api_token": encrypt_secret(body.api_token),
        "connected_at": datetime.now(UTC).isoformat(),
    }
    org.config = config
    await db.commit()

    return JiraConnectionStatus(
        connected=True,
        cloud_id=site_id,
        site_name=info.get("serverTitle", ""),
    )


@router.delete(
    "/connect",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("integrations:configure"))],
)
async def disconnect_jira(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove Jira credentials from org config."""
    from app.models.organization import Organization

    org = await db.get(Organization, current_user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    config = dict(org.config or {})
    config.pop("jira", None)
    org.config = config
    await db.commit()


# ── Project Listing ───────────────────────────────────────────────


@router.get("/projects", dependencies=[Depends(require_permissions("integrations:view"))])
async def list_jira_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List accessible Jira projects."""
    client = await _get_jira_client(db, current_user.org_id)
    projects = await client.list_projects()
    return [
        {
            "key": p.get("key"),
            "name": p.get("name"),
            "lead": p.get("lead", {}).get("displayName"),
        }
        for p in projects
    ]


# ── Discovery ─────────────────────────────────────────────────────


@router.post(
    "/discover",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("integrations:configure"))],
)
async def discover_jira_project(
    body: JiraDiscoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Scan a Jira project and return preview data (async job)."""
    jira_settings = await _get_jira_settings_or_404(db, current_user.org_id)

    # Create session in DISCOVERING state
    session_repo = JiraImportSessionRepository(db, org_id=current_user.org_id)
    session = JiraImportSession(
        org_id=current_user.org_id,
        jira_project_key=body.project_key,
        jira_project_name=body.project_key,
        jira_site_id=jira_settings.site_id,
        status=ImportStatus.DISCOVERING,
        created_by=current_user.id,
    )
    await session_repo.create(session)
    await db.commit()

    # Enqueue discovery job
    from app.services.job_queue import JOB_JIRA_DISCOVERY, create_job

    job = create_job(
        JOB_JIRA_DISCOVERY,
        payload=JiraDiscoveryPayload(
            org_id=str(current_user.org_id),
            session_id=str(session.id),
            project_key=body.project_key,
            jql_filter=body.jql_filter,
        ).model_dump(),
        user_id=str(current_user.id),
    )

    session.job_id = job.job_id
    await db.commit()

    return {"jobId": job.job_id, "sessionId": str(session.id)}


# ── Import ────────────────────────────────────────────────────────


@router.post(
    "/import",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("integrations:configure"))],
)
async def start_jira_import(
    body: JiraImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start the Jira import pipeline (async job)."""
    session_repo = JiraImportSessionRepository(db, org_id=current_user.org_id)
    session = await session_repo.get_by_id(body.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Import session not found")
    if session.status not in (ImportStatus.READY, ImportStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail=f"Session is in {session.status} state, not ready for import",
        )

    # Save import config
    session.config = {
        "consolidation_mode": body.consolidation_mode,
        "status_mappings": {m.jira_status: m.bud_status for m in body.status_mappings},
        "type_mappings": {m.jira_type: m.target for m in body.type_mappings},
        "include_active": body.include_active,
    }
    session.status = ImportStatus.PENDING
    session.processed_count = 0
    session.error = None
    await db.flush()

    # Enqueue import job
    from app.services.job_queue import JOB_JIRA_IMPORT, create_job

    job = create_job(
        JOB_JIRA_IMPORT,
        payload=JiraImportPayload(
            org_id=str(current_user.org_id),
            session_id=str(session.id),
        ).model_dump(),
        user_id=str(current_user.id),
    )

    session.job_id = job.job_id
    await db.commit()

    return {"jobId": job.job_id, "sessionId": str(session.id)}


# ── Sessions ──────────────────────────────────────────────────────


@router.get(
    "/sessions",
    response_model=list[JiraImportSessionList],
    dependencies=[Depends(require_permissions("integrations:view"))],
)
async def list_import_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[JiraImportSession]:
    """List all import sessions for the current org."""
    repo = JiraImportSessionRepository(db, org_id=current_user.org_id)
    return await repo.list_sessions()


@router.get(
    "/sessions/{session_id}",
    response_model=JiraImportSessionRead,
    dependencies=[Depends(require_permissions("integrations:view"))],
)
async def get_import_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JiraImportSession:
    """Get a single import session with reconciliation report."""
    repo = JiraImportSessionRepository(db, org_id=current_user.org_id)
    session = await repo.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Import session not found")
    return session


@router.get(
    "/sessions/{session_id}/review-items",
    dependencies=[Depends(require_permissions("integrations:view"))],
)
async def get_review_items(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get items flagged for manual duplicate review."""
    map_repo = JiraIssueBudMapRepository(db, org_id=current_user.org_id)
    items = await map_repo.get_review_needed(session_id)
    return [
        {
            "id": str(item.id),
            "jiraKey": item.jira_issue_key,
            "jiraType": item.jira_issue_type,
            "status": item.status,
            "note": item.note,
            "budId": str(item.bud_id) if item.bud_id else None,
        }
        for item in items
    ]


# ── Enrichment ────────────────────────────────────────────────────


@router.post(
    "/sessions/{session_id}/enrich",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("integrations:configure"))],
)
async def enrich_imported_buds(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger AI enrichment (PRD agent) on all BUDs from an import session."""
    session_repo = JiraImportSessionRepository(db, org_id=current_user.org_id)
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Import session not found")
    if session.status != "completed":
        raise HTTPException(status_code=400, detail="Session must be completed before enriching")

    from app.services.job_queue import JOB_JIRA_ENRICH, create_job

    job = create_job(
        JOB_JIRA_ENRICH,
        payload={
            "org_id": str(current_user.org_id),
            "session_id": str(session_id),
            "triggered_by": str(current_user.id),
        },
        user_id=str(current_user.id),
    )
    return {"jobId": job.job_id, "sessionId": str(session_id)}


# ── Review Actions ────────────────────────────────────────────────


class ReviewActionRequest(PydanticBaseModel):
    """Request body for acting on a review item."""

    action: str  # "skip" | "import" | "merge"


@router.post(
    "/review/{map_id}/action",
    dependencies=[Depends(require_permissions("integrations:configure"))],
)
async def review_item_action(
    map_id: uuid.UUID,
    body: ReviewActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Act on a review-needed item: skip, import, or merge."""
    map_repo = JiraIssueBudMapRepository(db, org_id=current_user.org_id)
    entry = await map_repo.get_by_id(map_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Map entry not found")
    if entry.status != "review_needed":
        raise HTTPException(status_code=400, detail="Item is not in review_needed status")

    from app.models.jira_import import MapStatus

    if body.action == "skip":
        await map_repo.mark_status(map_id, MapStatus.SKIPPED, note="Skipped by user")
        await db.commit()
        return {"status": "skipped", "mapId": str(map_id)}

    if body.action == "import":
        # Force-create a BUD from this Jira issue's stored data
        bud_id = await _create_bud_from_map_entry(db, current_user.org_id, entry)
        await map_repo.mark_status(map_id, MapStatus.IMPORTED, bud_id=bud_id)
        await db.commit()
        return {"status": "imported", "mapId": str(map_id), "budId": str(bud_id)}

    if body.action == "merge":
        # Link to the existing similar BUD (don't create new)
        if not entry.bud_id:
            raise HTTPException(status_code=400, detail="No similar BUD to merge into")
        await map_repo.mark_status(
            map_id,
            MapStatus.CONSOLIDATED,
            bud_id=entry.bud_id,
            note="Merged into existing BUD by user",
        )
        await db.commit()
        return {"status": "merged", "mapId": str(map_id), "budId": str(entry.bud_id)}

    raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")


async def _create_bud_from_map_entry(
    db: AsyncSession,
    org_id: uuid.UUID,
    entry: "JiraIssueBudMap",
) -> uuid.UUID:
    """Create a BUD from a review-needed map entry's stored Jira data."""
    import contextlib
    import json

    from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEventType
    from app.repositories.bud import BUDRepository
    from app.services.bud_timeline import record_event
    from app.services.embedding_service import embedding_service

    # Parse stored BUD data from map entry note (JSON)
    stored: dict[str, Any] = {}
    if entry.note:
        with contextlib.suppress(json.JSONDecodeError):
            stored = json.loads(entry.note)

    title = stored.get("title") or entry.jira_issue_key
    requirements = stored.get("requirements_md") or f"*Imported from Jira {entry.jira_issue_key}*"
    metadata = stored.get("metadata") or {
        "source": "jira_import",
        "jira_key": entry.jira_issue_key,
    }

    bud_repo = BUDRepository(db, org_id=org_id)
    next_number = await bud_repo.next_bud_number()

    bud = BUDDocument(
        org_id=org_id,
        bud_number=next_number,
        title=title,
        status=BUDStatus.BUD,
        requirements_md=requirements,
        metadata_=metadata,
    )
    if stored.get("assignee_id"):
        bud.assignee_id = uuid.UUID(stored["assignee_id"])

    with contextlib.suppress(Exception):
        embed_text = f"{title} {requirements[:500]}"
        bud.embedding = await embedding_service.embed(embed_text)

    await bud_repo.create(bud)
    await record_event(
        db,
        org_id,
        bud.id,
        BUDTimelineEventType.CREATED,
        actor_name="Jira Import",
        detail={"source": "jira_import", "jira_key": entry.jira_issue_key},
    )
    return bud.id


# ── Helpers ───────────────────────────────────────────────────────


async def _get_jira_client(db: AsyncSession, org_id: uuid.UUID) -> JiraClient:
    """Build a JiraClient from org settings, or raise 400."""
    settings = await _get_jira_settings_or_404(db, org_id)
    return JiraClient(
        site_url=settings.site_url,
        email=settings.email,
        api_token=settings.api_token,
    )


async def _get_jira_settings_or_404(db: AsyncSession, org_id: uuid.UUID) -> JiraSettings:
    """Load Jira settings from org config, or raise 400 if not connected."""
    from app.models.organization import Organization
    from app.services.org_settings import get_jira_settings

    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    settings = get_jira_settings(org.config)
    if not settings.is_connected:
        raise HTTPException(
            status_code=400,
            detail="Jira is not connected. Configure credentials in Settings first.",
        )
    return settings
