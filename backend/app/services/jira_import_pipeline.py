# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Jira import pipeline — discovery and import job handlers.

Two job handlers registered with the job queue:
- ``handle_discovery_job``: Scan a Jira project and return preview data.
- ``handle_import_job``: Execute the 5-phase import pipeline.

Both handlers create their own DB sessions (background job pattern)
and report progress via ``update_job()``.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jira_import import ImportStatus, MapStatus
from app.repositories.jira_import import JiraIssueBudMapRepository
from app.schemas.jira_import import (
    DiscoveryResult,
    FailedItem,
    ImportedCounts,
    JiraDiscoveryPayload,
    JiraImportPayload,
    ReconciliationReport,
    ReviewItem,
    SkippedCounts,
)
from app.services.jira_client import JiraClient
from app.services.jira_consolidator import (
    ConsolidatedGroup,
    build_consolidated_requirements,
    consolidate_issues,
)
from app.services.jira_field_mapper import (
    JiraFieldMapper,
    build_user_cache_from_issues,
)
from app.services.jira_import_helpers import (
    cleanup_orphaned_map_entries as _cleanup_orphaned_map_entries,
)
from app.services.jira_import_helpers import (
    count_by_issue_type,
    create_map_entry,
    get_org,
    mark_session_failed,
    resolve_users,
)
from app.services.job_queue import JobState, update_job

logger = structlog.get_logger(__name__)

# Safety limit: reject imports larger than this. Use JQL filter to narrow scope.
_MAX_ISSUES = 5000

# Default JQL filter: import only backlog items (not started, not done).
# Closed/resolved issues are already done — no value importing them.
# In-progress/testing items are actively being worked on — importing would
# create duplicates of work already tracked elsewhere.
# Users can override this via the import config's include_active flag.
_BACKLOG_ONLY_FILTER = 'statusCategory != "Done" AND statusCategory != "In Progress"'

# Progress weights by phase (must sum to 100)
_WEIGHT_EXTRACT = 40
_WEIGHT_TRANSFORM = 5
_WEIGHT_CONSOLIDATE = 5
_WEIGHT_DEDUP = 15
_WEIGHT_LOAD = 30
_WEIGHT_VERIFY = 5

_BATCH_COMMIT_SIZE = 50


# ── Discovery Job Handler ─────────────────────────────────────────


async def handle_discovery_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Scan a Jira project and populate the session's discovery_result.

    Steps:
    1. Count issues by JQL
    2. List issue types and statuses
    3. Fetch 5 sample issues
    4. Check how many are already imported
    5. Estimate import time
    """
    payload = JiraDiscoveryPayload(**raw_payload)
    org_id = uuid.UUID(payload.org_id)
    session_id = uuid.UUID(payload.session_id)

    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        client: JiraClient | None = None
        try:
            update_job(job_id, state=JobState.RUNNING, status_message="Connecting to Jira...")

            from app.services.org_settings import get_jira_settings

            org = await get_org(db, org_id)
            jira_settings = get_jira_settings(org.config)
            client = JiraClient(
                site_url=jira_settings.site_url,
                email=jira_settings.email,
                api_token=jira_settings.api_token,
            )

            jql = f'project = "{payload.project_key}" AND {_BACKLOG_ONLY_FILTER}'
            if payload.jql_filter:
                jql = f"{jql} AND ({payload.jql_filter})"

            update_job(job_id, status_message="Counting backlog issues...", progress_pct=10)
            total = await client.count_issues(jql)

            update_job(job_id, status_message="Fetching project metadata...", progress_pct=30)

            # Get issue type counts via separate queries
            type_counts = await count_by_issue_type(client, payload.project_key, jql)
            statuses = await client.get_project_statuses(payload.project_key)
            status_names = [s.get("name", "") for s in statuses]

            update_job(job_id, status_message="Fetching sample issues...", progress_pct=60)

            # Fetch 5 sample issues for preview
            sample_issues: list[dict] = []
            async for batch in client.search_issues(f"{jql} ORDER BY created DESC", start_at=0):
                for issue in batch[:5]:
                    sample_issues.append(
                        {
                            "key": issue.get("key"),
                            "summary": issue.get("fields", {}).get("summary"),
                            "type": issue.get("fields", {}).get("issuetype", {}).get("name"),
                            "status": issue.get("fields", {}).get("status", {}).get("name"),
                        }
                    )
                break  # Only need first page

            # Check already-imported count (only keys from THIS project)
            from app.repositories.jira_import import JiraIssueBudMapRepository

            map_repo = JiraIssueBudMapRepository(db, org_id=org_id)
            existing_keys = await map_repo.get_existing_keys_for_org()
            # Filter to keys from this project (e.g. "BOOD-" prefix)
            project_prefix = f"{payload.project_key}-"
            already_imported = sum(1 for k in existing_keys if k.startswith(project_prefix))
            new_to_import = max(0, total - already_imported)

            # Estimate time based on new issues only
            estimated_seconds = max(12, (new_to_import * 3) // 10)

            discovery = DiscoveryResult(
                project_key=payload.project_key,
                project_name=payload.project_key,
                total_issues=total,
                by_type=type_counts,
                statuses_found=status_names,
                estimated_time_seconds=estimated_seconds,
                already_imported_count=already_imported,
                sample_issues=sample_issues,
            )

            # Update session
            from app.repositories.jira_import import JiraImportSessionRepository

            session_repo = JiraImportSessionRepository(db, org_id=org_id)
            session = await session_repo.get_by_id(session_id)
            if session:
                session.discovery_result = discovery.model_dump(by_alias=True)
                session.total_issues = total
                session.status = ImportStatus.READY
                await db.flush()

            await db.commit()

            update_job(
                job_id,
                state=JobState.COMPLETED,
                status_message="Discovery complete",
                progress_pct=100,
                result=discovery.model_dump(by_alias=True),
            )

        except Exception as exc:
            await db.rollback()
            logger.exception("jira_discovery_failed", session_id=str(session_id))
            await mark_session_failed(db, org_id, session_id, str(exc))
            update_job(
                job_id,
                state=JobState.FAILED,
                error=str(exc)[:500],
                status_message="Discovery failed",
            )
        finally:
            if client:
                await client.close()


# ── Import Job Handler ────────────────────────────────────────────


async def handle_import_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Execute the 5-phase Jira import pipeline.

    Phases:
    1. Extract — paginated fetch from Jira API
    2. Transform — ADF→MD, field mapping
    3. Consolidate — Epic grouping, sub-task folding
    4. Dedup — Layer 2 semantic check against existing BUDs
    5. Load — Create BUD/Bug records + verify
    """
    payload = JiraImportPayload(**raw_payload)
    org_id = uuid.UUID(payload.org_id)
    session_id = uuid.UUID(payload.session_id)

    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        client: JiraClient | None = None
        try:
            update_job(job_id, state=JobState.RUNNING, status_message="Starting import...")

            # Load session config
            from app.repositories.jira_import import (
                JiraImportSessionRepository,
                JiraIssueBudMapRepository,
            )

            session_repo = JiraImportSessionRepository(db, org_id=org_id)
            session = await session_repo.get_by_id(session_id)
            if not session:
                raise ValueError(f"Import session {session_id} not found")

            session.status = ImportStatus.RUNNING
            session.job_id = job_id
            await db.flush()

            config = session.config or {}
            consolidation_mode = config.get("consolidation_mode", "epic")
            status_mappings = config.get("status_mappings", {})
            type_mappings = config.get("type_mappings", {})

            # Build Jira client
            from app.services.org_settings import get_jira_settings

            org = await get_org(db, org_id)
            jira_settings = get_jira_settings(org.config)
            client = JiraClient(
                site_url=jira_settings.site_url,
                email=jira_settings.email,
                api_token=jira_settings.api_token,
            )

            # Clean up orphaned map entries (BUD deleted but map entry remains)
            # and stale entries from previous failed imports
            map_repo = JiraIssueBudMapRepository(db, org_id=org_id)
            await _cleanup_orphaned_map_entries(db, org_id)
            await db.commit()

            # Get existing keys for Layer 1 dedup
            existing_keys = await map_repo.get_existing_keys_for_org()

            # ── Phase 1: Extract ──────────────────────────────────
            update_job(job_id, status_message="Extracting issues from Jira...")

            pk = session.jira_project_key
            include_active = config.get("include_active", False)
            base_filter = "" if include_active else f" AND {_BACKLOG_ONLY_FILTER}"
            jql = f'project = "{pk}"{base_filter} ORDER BY created ASC'
            custom_jql = config.get("jql_filter")
            if custom_jql:
                jql = f'project = "{pk}"{base_filter} AND ({custom_jql}) ORDER BY created ASC'

            all_issues: list[dict] = []
            page_num = 0
            total = session.total_issues or 0
            resume_at = session.processed_count or 0

            async for batch in client.search_issues(jql, start_at=resume_at):
                # Layer 1: skip already-imported keys
                new_issues = [i for i in batch if i.get("key") not in existing_keys]
                all_issues.extend(new_issues)

                if len(all_issues) > _MAX_ISSUES:
                    raise ValueError(
                        f"Import exceeds {_MAX_ISSUES} new issues. "
                        "Use a JQL filter to narrow the scope."
                    )

                page_num += 1
                processed = resume_at + len(all_issues)
                pct = int(_WEIGHT_EXTRACT * min(processed / max(total, 1), 1.0))
                update_job(
                    job_id,
                    status_message=f"Extracting: {processed}/{total} issues",
                    progress_pct=pct,
                )

                # Checkpoint progress
                if new_issues:
                    last_key = new_issues[-1].get("key", "")
                    await session_repo.update_progress(session_id, processed, last_key)
                    await db.commit()

            skipped_existing = max(0, (total - resume_at) - len(all_issues))

            # ── Phase 2: Transform ────────────────────────────────
            pct_base = _WEIGHT_EXTRACT
            update_job(
                job_id,
                status_message="Building user map...",
                progress_pct=pct_base,
            )

            # Build user email → UUID cache
            all_emails = build_user_cache_from_issues(all_issues)
            user_cache = await resolve_users(db, org_id, all_emails)

            mapper = JiraFieldMapper(
                status_map=status_mappings,
                type_map=type_mappings,
                user_cache=user_cache,
            )

            pct_base += _WEIGHT_TRANSFORM
            update_job(
                job_id,
                status_message="Consolidating issues...",
                progress_pct=pct_base,
            )

            # ── Phase 3: Consolidate ──────────────────────────────
            groups, standalone_bugs = consolidate_issues(
                all_issues, mode=consolidation_mode, mapper=mapper
            )

            pct_base += _WEIGHT_CONSOLIDATE
            update_job(
                job_id,
                status_message=f"Loading {len(groups)} BUDs + {len(standalone_bugs)} bugs...",
                progress_pct=pct_base,
            )

            # ── Phase 4 + 5: Dedup + Load ─────────────────────────
            report = await _load_groups(
                db=db,
                org_id=org_id,
                session_id=session_id,
                groups=groups,
                standalone_bugs=standalone_bugs,
                mapper=mapper,
                map_repo=map_repo,
                job_id=job_id,
                pct_base=pct_base,
                skipped_existing=skipped_existing,
                total_jira_issues=total,
            )

            # Finalize session
            session.status = ImportStatus.COMPLETED
            session.result = report.model_dump(by_alias=True)
            session.processed_count = total
            await db.commit()

            update_job(
                job_id,
                state=JobState.COMPLETED,
                status_message="Import complete",
                progress_pct=100,
                result=report.model_dump(by_alias=True),
            )

        except Exception as exc:
            await db.rollback()
            logger.exception("jira_import_failed", session_id=str(session_id))
            await mark_session_failed(db, org_id, session_id, str(exc))
            update_job(
                job_id,
                state=JobState.FAILED,
                error=str(exc)[:500],
                status_message="Import failed",
            )
        finally:
            if client:
                await client.close()


# ── Load Phase (creates BUDs, Bugs, mappings) ────────────────────


async def _load_groups(
    *,
    db: AsyncSession,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
    groups: list[ConsolidatedGroup],
    standalone_bugs: list[dict],
    mapper: JiraFieldMapper,
    map_repo: JiraIssueBudMapRepository,
    job_id: str,
    pct_base: int,
    skipped_existing: int,
    total_jira_issues: int,
) -> ReconciliationReport:
    """Create BUDs and Bugs from consolidated groups."""

    from app.services.embedding_service import embedding_service
    from app.services.jira_dedup import check_semantic_duplicate

    # Tracking
    review_items: list[ReviewItem] = []
    failed_items: list[FailedItem] = []

    total_work = len(groups) + len(standalone_bugs)
    dedup_weight = _WEIGHT_DEDUP + _WEIGHT_LOAD

    for i, group in enumerate(groups):
        try:
            # Build BUD fields for dedup check
            requirements = build_consolidated_requirements(group, mapper)
            primary_fields = mapper.map_to_bud_fields(group.primary)
            title = primary_fields["title"]

            # Generate embedding for dedup similarity check
            embed_text = f"{title} {requirements[:500]}"
            try:
                vector = await embedding_service.embed(embed_text)
            except Exception:
                vector = None

            # Check semantic similarity against existing BUDs
            dedup_note: str | None = None
            matched_bud_id: uuid.UUID | None = None
            matched_bud_number: int | None = None
            if vector:
                dedup_result = await check_semantic_duplicate(
                    db, org_id, vector, exclude_bud_ids=set()
                )
                if dedup_result.matched_bud_id:
                    matched_bud_id = dedup_result.matched_bud_id
                    matched_bud_number = dedup_result.matched_bud_number
                    dedup_note = dedup_result.note

            # Store mapped data as JSON in note so _create_bud_from_map_entry can use it
            import json

            stored_data = json.dumps(
                {
                    "title": title,
                    "requirements_md": requirements,
                    "metadata": primary_fields.get("metadata_"),
                    "assignee_id": primary_fields.get("assignee_id"),
                    "dedup_note": dedup_note,
                }
            )

            # Create REVIEW_NEEDED entry — user decides whether to import
            await create_map_entry(
                map_repo,
                org_id,
                session_id,
                group.primary_key,
                group.primary,
                status=MapStatus.REVIEW_NEEDED,
                bud_id=matched_bud_id,
                note=stored_data,
            )

            # Track children/subtasks under the primary key
            for child in group.children:
                await create_map_entry(
                    map_repo,
                    org_id,
                    session_id,
                    child.get("key", ""),
                    child,
                    status=MapStatus.REVIEW_NEEDED,
                    consolidated_into=group.primary_key,
                    note=f"Child of {group.primary_key}",
                )

            for st in group.subtasks:
                await create_map_entry(
                    map_repo,
                    org_id,
                    session_id,
                    st.get("key", ""),
                    st,
                    status=MapStatus.REVIEW_NEEDED,
                    consolidated_into=group.primary_key,
                    note=f"Subtask of {group.primary_key}",
                )

            # Extract summary + description preview for the review UI
            primary_summary = group.primary.get("fields", {}).get("summary", "") or ""
            desc_preview = requirements[:150].replace("\n", " ") if requirements else ""

            review_items.append(
                ReviewItem(
                    jira_key=group.primary_key,
                    summary=primary_summary,
                    description_preview=desc_preview,
                    issue_type=(
                        group.primary.get("fields", {}).get("issuetype", {}).get("name", "")
                    ),
                    similar_to_bud=matched_bud_number,
                    distance=dedup_result.distance
                    if vector and dedup_result.matched_bud_id
                    else 0,
                )
            )

        except Exception as exc:
            failed_items.append(FailedItem(jira_key=group.primary_key, error=str(exc)[:200]))
            logger.warning("jira_group_failed", key=group.primary_key, error=str(exc))

        # Batch commit
        if (i + 1) % _BATCH_COMMIT_SIZE == 0:
            await db.commit()

        # Progress
        pct = pct_base + int(dedup_weight * (i + 1) / max(total_work, 1))
        update_job(
            job_id,
            status_message=f"Processed {i + 1}/{len(groups)} groups...",
            progress_pct=min(pct, 95),
        )

    # Standalone bugs — also create as review entries
    for bug_issue in standalone_bugs:
        try:
            await create_map_entry(
                map_repo,
                org_id,
                session_id,
                bug_issue.get("key", ""),
                bug_issue,
                status=MapStatus.REVIEW_NEEDED,
                note="Bug — will be created as Bug record",
            )
            bug_summary = bug_issue.get("fields", {}).get("summary", "") or ""
            review_items.append(
                ReviewItem(
                    jira_key=bug_issue.get("key", ""),
                    summary=bug_summary,
                    description_preview="",
                    issue_type="Bug",
                    similar_to_bud=None,
                    distance=0,
                )
            )
        except Exception as exc:
            key = bug_issue.get("key", "?")
            failed_items.append(FailedItem(jira_key=key, error=str(exc)[:200]))

    await db.commit()

    return ReconciliationReport(
        total_jira_issues=total_jira_issues,
        imported=ImportedCounts(
            buds_created=0,  # No auto-creation — user decides via review
            bugs_created=0,
            consolidated_into_epics=0,
            subtasks_folded=0,
        ),
        skipped=SkippedCounts(
            exact_duplicates=skipped_existing,
            semantic_duplicates=0,
            merged_similar=0,
        ),
        review_needed=review_items,
        failed=failed_items,
    )
