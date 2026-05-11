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

"""Shared helper functions for the Jira import pipeline.

Extracted from ``jira_import_pipeline.py`` to keep file sizes
manageable. Contains: bug creation, map entry creation, user
resolution, org loading, session failure marking, issue type counting.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bug import Bug, BugType
from app.models.jira_import import ImportStatus, JiraIssueBudMap
from app.repositories.jira_import import JiraImportSessionRepository, JiraIssueBudMapRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.schemas.jira_import import IssueTypeCount
from app.services.embedding_service import embedding_service
from app.services.jira_client import JiraClient
from app.services.jira_consolidator import ConsolidatedGroup
from app.services.jira_field_mapper import JiraFieldMapper

logger = structlog.get_logger(__name__)


async def create_bug(
    db: AsyncSession,
    org_id: uuid.UUID,
    issue: dict,
    mapper: JiraFieldMapper,
    bud_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Create a Bug record from a Jira bug issue.

    Finds the first org member as reporter since imports have no real reporter.

    Raises:
        ValueError: If the org has no members.
    """
    fields = mapper.map_to_bug_fields(issue)

    # Use first org member as fallback reporter
    reporter_id = await UserRepository(db).get_first_member_id(org_id)
    if not reporter_id:
        raise ValueError("No org members found — cannot assign bug reporter")

    bug = Bug(
        org_id=org_id,
        bud_id=bud_id,
        title=fields["title"],
        description=fields.get("description"),
        severity=fields.get("severity", "medium"),
        status=fields.get("status", "open"),
        bug_type=BugType.PRODUCTION,
        module=fields.get("module"),
        reporter_id=reporter_id,
    )
    if fields.get("assignee_id"):
        bug.assignee_id = uuid.UUID(fields["assignee_id"])

    db.add(bug)
    await db.flush()
    await db.refresh(bug)

    # Generate embedding
    try:
        text = bug.title
        if bug.description:
            text = f"{text} {bug.description[:500]}"
        bug.embedding = await embedding_service.embed(text)
        await db.flush()
    except Exception:
        logger.warning("bug_embedding_failed_on_import", bug_id=str(bug.id))

    return bug.id


async def create_map_entry(
    map_repo: JiraIssueBudMapRepository,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
    jira_key: str,
    issue: dict | None,
    *,
    status: str,
    bud_id: uuid.UUID | None = None,
    bug_id: uuid.UUID | None = None,
    note: str | None = None,
    consolidated_into: str | None = None,
) -> None:
    """Create a JiraIssueBudMap entry for traceability.

    If a duplicate key exists, deletes the old entry first (handles
    re-imports after BUD deletion).
    """
    if not jira_key:
        return

    # Delete any existing entry for this key to avoid unique constraint violation
    existing = await map_repo.get_by_jira_key(jira_key)
    if existing:
        await map_repo.delete_by_id(existing.id)

    entry = JiraIssueBudMap(
        org_id=org_id,
        import_session_id=session_id,
        jira_issue_key=jira_key,
        jira_issue_id=(issue or {}).get("id", ""),
        jira_issue_type=(
            (issue or {}).get("fields", {}).get("issuetype", {}).get("name", "Unknown")
        ),
        status=status,
        bud_id=bud_id,
        bug_id=bug_id,
        note=note,
        consolidated_into=consolidated_into,
    )
    await map_repo.add(entry)


async def resolve_users(
    db: AsyncSession,
    org_id: uuid.UUID,
    emails: set[str],
) -> dict[str, str]:
    """Bulk-resolve Jira emails to Bodhiorchard user UUIDs.

    Returns dict of lowercase email → UUID string.
    """
    matched = await UserRepository(db).map_emails_to_ids(org_id, emails)
    return {email: str(uid) for email, uid in matched.items()}


async def get_org(db: AsyncSession, org_id: uuid.UUID) -> Any:
    """Fetch organization by ID.

    Raises:
        ValueError: If not found.
    """
    org = await OrganizationRepository(db).get_by_id(org_id)
    if not org:
        raise ValueError(f"Organization {org_id} not found")
    return org


async def mark_session_failed(
    db: AsyncSession,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
    error: str,
) -> None:
    """Mark an import session as failed (best-effort)."""
    try:
        repo = JiraImportSessionRepository(db, org_id=org_id)
        await repo.update_status(session_id, ImportStatus.FAILED, error=error)
        await db.commit()
    except Exception:
        logger.warning("failed_to_mark_session_failed", session_id=str(session_id))


async def count_by_issue_type(
    client: JiraClient,
    project_key: str,
    base_jql: str,
) -> list[IssueTypeCount]:
    """Count issues by type by sampling the first few pages of results."""
    total = await client.count_issues(base_jql)
    if total == 0:
        return []

    type_counts: dict[str, int] = {}
    async for batch in client.search_issues(base_jql, fields=["issuetype"], start_at=0):
        for issue in batch:
            itype = issue.get("fields", {}).get("issuetype", {}).get("name", "Unknown")
            type_counts[itype] = type_counts.get(itype, 0) + 1
        if sum(type_counts.values()) >= min(total, 500):
            break

    return [
        IssueTypeCount(issue_type=name, count=count)
        for name, count in sorted(type_counts.items(), key=lambda x: -x[1])
    ]


async def cleanup_orphaned_map_entries(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Delete ALL map entries that are no longer backed by a real BUD/Bug.

    Covers:
    - Entries with bud_id pointing to a deleted BUD
    - Entries with bug_id pointing to a deleted Bug
    - Entries with no bud_id and no bug_id (stale from abandoned imports)

    This ensures re-importing a project after deleting BUDs works
    without hitting the unique constraint on (org_id, jira_issue_key).
    """
    map_repo = JiraIssueBudMapRepository(db, org_id=org_id)
    total = await map_repo.delete_orphaned(
        valid_bud_ids_select=select(BUDDocument.id).where(BUDDocument.org_id == org_id),
        valid_bug_ids_select=select(Bug.id).where(Bug.org_id == org_id),
    )
    if total:
        logger.info("cleaned_orphaned_map_entries", count=total, org_id=str(org_id))
    return total


def find_issue_in_group(group: ConsolidatedGroup, key: str) -> dict | None:
    """Find an issue dict by key within a consolidated group."""
    if group.primary.get("key") == key:
        return group.primary
    for child in group.children:
        if child.get("key") == key:
            return child
    for st in group.subtasks:
        if st.get("key") == key:
            return st
    for bug in group.bugs:
        if bug.get("key") == key:
            return bug
    return None
