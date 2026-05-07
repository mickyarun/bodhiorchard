# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Standup aggregation service.

Generates daily standup reports by querying existing activity tables
(DevActivityLog, PullRequest, BUDTimelineEvent, Bug, AgentActivityLog,
RewardEvent). No external API calls — all data already lives in PostgreSQL.

Time window: from the last standup's creation timestamp (or 24h fallback)
up to ``until`` (defaults to now).
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDStatus
from app.models.standup import StandupReport
from app.repositories.agent_activity import AgentActivityLogRepository
from app.repositories.bud import BUDRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.bug import BugRepository
from app.repositories.dev_activity import DevActivityLogRepository
from app.repositories.developer_xp import RewardEventRepository
from app.repositories.pull_request import PullRequestRepository
from app.repositories.standup import StandupReportRepository
from app.repositories.user import UserRepository
from app.schemas.standup import (
    BUDTransition,
    MemberStandupItem,
    StandupFlag,
    StandupReportRead,
)

logger = structlog.get_logger(__name__)


# ─── Public API ─────────────────────────────────────────────────────────────


async def get_or_generate_today(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> StandupReport:
    """Return today's standup, generating it if it doesn't exist yet.

    Handles concurrent requests gracefully: if two callers race past
    the existence check, the second commit hits ``uq_standup_org_date``
    and we fall back to reading the winner's row.
    """
    today = datetime.now(UTC).date()
    existing = await _get_report_by_date(db, org_id, today)
    if existing:
        return existing
    try:
        return await generate_standup(db, org_id, today)
    except IntegrityError:
        await db.rollback()
        existing = await _get_report_by_date(db, org_id, today)
        if existing:
            return existing
        raise


async def get_report_by_date(
    db: AsyncSession,
    org_id: uuid.UUID,
    target_date: date,
) -> StandupReport | None:
    """Return a standup report for a specific date, or None."""
    return await _get_report_by_date(db, org_id, target_date)


async def list_recent(
    db: AsyncSession,
    org_id: uuid.UUID,
    limit: int = 14,
) -> list[StandupReport]:
    """Return the most recent standup reports for an org."""
    return await StandupReportRepository(db, org_id=org_id).list_recent(limit=limit)


async def generate_standup(
    db: AsyncSession,
    org_id: uuid.UUID,
    target_date: date,
) -> StandupReport:
    """Generate a standup report by aggregating existing DB data.

    Time window: from the previous standup's timestamp (or 24h fallback)
    until the end of target_date.
    """
    since = await _get_since_timestamp(db, org_id, target_date)
    until = datetime.combine(target_date, datetime.max.time(), tzinfo=UTC)

    # Collect all org members first (authoritative membership)
    members = await _collect_members(db, org_id)

    # Build per-member activity dicts keyed by user_id
    dev_activity = await _collect_dev_activity(db, org_id, since, until)
    pr_activity = await _collect_pr_activity(db, org_id, since, until)
    bud_transitions = await _collect_bud_transitions(db, org_id, since, until)
    bug_activity = await _collect_bug_activity(db, org_id, since, until)
    agent_completions = await _collect_agent_completions(db, org_id, since, until)
    xp_earned = await _collect_xp_earned(db, org_id, since, until)

    # Merge into MemberStandupItem per member
    member_items: list[MemberStandupItem] = []
    for uid, name, avatar_url, level, level_name in members:
        uid_str = str(uid)
        dev = dev_activity.get(uid, {})
        pr = pr_activity.get(uid, {})
        bug = bug_activity.get(uid, {})

        item = MemberStandupItem(
            user_id=uid_str,
            name=name or "",
            avatar_url=avatar_url,
            level=level or 1,
            level_name=level_name or "seedling",
            commits_count=dev.get("commits", 0),
            files_changed=dev.get("files_changed", 0),
            prs_opened=pr.get("opened", 0),
            prs_merged=pr.get("merged", 0),
            buds_transitioned=bud_transitions.get(uid, []),
            bugs_filed=bug.get("filed", 0),
            bugs_resolved=bug.get("resolved", 0),
            xp_earned=xp_earned.get(uid, 0),
            agent_tasks_completed=agent_completions.get(uid, 0),
        )
        member_items.append(item)

    # Detect risk flags
    flags = await _detect_flags(db, org_id, member_items)

    # Attach per-member flags
    for flag in flags:
        if flag.user_id:
            for item in member_items:
                if item.user_id == flag.user_id:
                    item.flags.append(flag)
                    break

    # Persist
    report = StandupReport(
        org_id=org_id,
        date=target_date,
        content={
            "members": [m.model_dump() for m in member_items],
            "since": since.isoformat(),
        },
        flags={"flags": [f.model_dump() for f in flags]},
        summary=None,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return report


# ─── Report Serialization ──────────────────────────────────────────────────


def report_to_read(report: StandupReport) -> StandupReportRead:
    """Convert a StandupReport ORM instance to the API response schema."""
    content = report.content or {}
    flags_data = report.flags or {}

    members = [MemberStandupItem(**m) for m in content.get("members", [])]
    flags = [StandupFlag(**f) for f in flags_data.get("flags", [])]

    return StandupReportRead(
        id=str(report.id),
        date=report.date,
        members=members,
        flags=flags,
        summary=report.summary,
        since_timestamp=content.get("since"),
        created_at=report.created_at,
    )


# ─── Private Helpers ────────────────────────────────────────────────────────


async def _get_report_by_date(
    db: AsyncSession,
    org_id: uuid.UUID,
    target_date: date,
) -> StandupReport | None:
    return await StandupReportRepository(db, org_id=org_id).get_by_date(target_date)


async def _get_since_timestamp(
    db: AsyncSession,
    org_id: uuid.UUID,
    target_date: date,
) -> datetime:
    """Get the start of the time window: previous standup's created_at, or 24h ago.

    Excludes the target_date itself so that re-generation or backfill
    scenarios don't accidentally use the current report's timestamp.
    """
    last_ts = await StandupReportRepository(db, org_id=org_id).get_previous_created_at(target_date)
    if last_ts:
        return last_ts.replace(tzinfo=UTC) if last_ts.tzinfo is None else last_ts
    return datetime.now(UTC) - timedelta(hours=24)


async def _collect_members(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> list[tuple[uuid.UUID, str | None, str | None, int | None, str | None]]:
    """Return all active org members with XP info."""
    return await UserRepository(db).list_active_member_xp_summary(org_id)


async def _collect_dev_activity(
    db: AsyncSession,
    org_id: uuid.UUID,
    since: datetime,
    until: datetime,
) -> dict[uuid.UUID, dict[str, int]]:
    """Aggregate commit and file_change counts per user from DevActivityLog."""
    counts = await DevActivityLogRepository(db, org_id=org_id).count_events_by_user_in_window(
        ["commit", "file_change"], since, until
    )
    out: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: {"commits": 0, "files_changed": 0})
    for (user_id, event_type), cnt in counts.items():
        if event_type == "commit":
            out[user_id]["commits"] = cnt
        elif event_type == "file_change":
            out[user_id]["files_changed"] = cnt
    return dict(out)


async def _collect_pr_activity(
    db: AsyncSession,
    org_id: uuid.UUID,
    since: datetime,
    until: datetime,
) -> dict[uuid.UUID, dict[str, int]]:
    """Count PRs opened and merged per user in the time window."""
    pr_repo = PullRequestRepository(db, org_id=org_id)
    opened = await pr_repo.count_opened_by_author_in_window(since, until)
    merged = await pr_repo.count_merged_by_author_in_window(since, until)
    out: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: {"opened": 0, "merged": 0})
    for user_id, cnt in opened.items():
        out[user_id]["opened"] = cnt
    for user_id, cnt in merged.items():
        out[user_id]["merged"] = cnt
    return dict(out)


async def _collect_bud_transitions(
    db: AsyncSession,
    org_id: uuid.UUID,
    since: datetime,
    until: datetime,
) -> dict[uuid.UUID, list[BUDTransition]]:
    """Collect BUD stage transitions (status_change events) per actor."""
    rows = await BUDTimelineRepository(db, org_id=org_id).list_status_changes_with_bud_in_window(
        since, until
    )
    out: dict[uuid.UUID, list[BUDTransition]] = defaultdict(list)
    for actor_id, bud_number, title, detail in rows:
        from_stage = (detail or {}).get("from", "")
        to_stage = (detail or {}).get("to", "")
        out[actor_id].append(
            BUDTransition(
                bud_number=bud_number,
                title=title or "",
                from_stage=from_stage,
                to_stage=to_stage,
            )
        )
    return dict(out)


async def _collect_bug_activity(
    db: AsyncSession,
    org_id: uuid.UUID,
    since: datetime,
    until: datetime,
) -> dict[uuid.UUID, dict[str, int]]:
    """Count bugs filed (by reporter) and resolved (by assignee) per user."""
    bug_repo = BugRepository(db, org_id=org_id)
    filed = await bug_repo.count_filed_by_reporter_in_window(since, until)
    resolved = await bug_repo.count_resolved_by_assignee_in_window(since, until)
    out: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: {"filed": 0, "resolved": 0})
    for reporter_id, cnt in filed.items():
        out[reporter_id]["filed"] = cnt
    for assignee_id, cnt in resolved.items():
        out[assignee_id]["resolved"] = cnt
    return dict(out)


async def _collect_agent_completions(
    db: AsyncSession,
    org_id: uuid.UUID,
    since: datetime,
    until: datetime,
) -> dict[uuid.UUID, int]:
    """Count completed agent tasks per user in the time window."""
    return await AgentActivityLogRepository(
        db, org_id=org_id
    ).count_skill_completions_by_user_in_window(since, until)


async def _collect_xp_earned(
    db: AsyncSession,
    org_id: uuid.UUID,
    since: datetime,
    until: datetime,
) -> dict[uuid.UUID, int]:
    """Sum XP earned per user in the time window."""
    return await RewardEventRepository(db, org_id=org_id).sum_xp_by_user_in_window(since, until)


# ─── Risk Flag Detection ───────────────────────────────────────────────────


async def _detect_flags(
    db: AsyncSession,
    org_id: uuid.UUID,
    member_items: list[MemberStandupItem],
) -> list[StandupFlag]:
    """Detect risk flags from member activity and BUD/bug state."""
    flags: list[StandupFlag] = []

    # Flag 1: No activity — member has zero events
    for m in member_items:
        total = (
            m.commits_count
            + m.files_changed
            + m.prs_opened
            + m.prs_merged
            + len(m.buds_transitioned)
            + m.bugs_filed
            + m.bugs_resolved
        )
        if total == 0:
            flags.append(
                StandupFlag(
                    type="no_activity",
                    severity="info",
                    description=f"{m.name} had no recorded activity",
                    user_id=m.user_id,
                    user_name=m.name,
                )
            )

    # Flag 2: BUDs lagging — in development/testing past deadline
    lagging_rows = await BUDRepository(db, org_id=org_id).list_lagging_in_statuses(
        [BUDStatus.DEVELOPMENT, BUDStatus.TESTING, BUDStatus.CODE_REVIEW]
    )
    for bud_number, title, status_val in lagging_rows:
        status_str = status_val.value if hasattr(status_val, "value") else str(status_val)
        flags.append(
            StandupFlag(
                type="bud_lagging",
                severity="warning",
                description=f"BUD-{bud_number} '{title}' is past deadline in {status_str}",
                bud_number=bud_number,
            )
        )

    # Flag 3: Critical bugs open
    crit_count = await BugRepository(db, org_id=org_id).count_critical_open()
    if crit_count > 0:
        flags.append(
            StandupFlag(
                type="critical_bugs",
                severity="critical",
                description=f"{crit_count} critical bug{'s' if crit_count > 1 else ''} open",
            )
        )

    return flags
