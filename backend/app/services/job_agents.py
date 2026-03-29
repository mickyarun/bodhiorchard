"""Agent job handler for Slack triage events.

Processes triage actions (start, continue, approve/reject) dispatched
from Slack webhooks via the async job queue.
"""

import asyncio
from typing import Any

import structlog

from app.models.agent_activity import AgentActivityLog
from app.services.event_bus import publish
from app.schemas.jobs import (
    JobState,
    TriageJobPayload,
)
from app.services.job_queue import update_job
from app.services.job_utils import (
    get_thread_key,
    thread_locks,
)

logger = structlog.get_logger(__name__)


# ── Triage handler ─────────────────────────────────────────────────


async def handle_triage_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Process a Slack triage event (start, continue, or approve/reject)."""
    payload = TriageJobPayload(**raw_payload)

    update_job(job_id, status_message=f"Processing {payload.action}...", progress_pct=10)

    thread_key = get_thread_key(payload.event_data)
    lock = thread_locks.setdefault(thread_key, asyncio.Lock())

    async with lock:
        from app.core.encryption import decrypt_secret
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            try:
                from app.api.v1.slack import _resolve_org_by_team_id

                org = await _resolve_org_by_team_id(db, payload.team_id)
                if org is None:
                    update_job(
                        job_id,
                        state=JobState.FAILED,
                        error=f"Organization not found for team {payload.team_id}",
                    )
                    return

                # Log skill_invoked
                db.add(AgentActivityLog(
                    org_id=org.id,
                    event_type="skill_invoked",
                    status="in_progress",
                    message=f"Triage '{payload.action}' started",
                    source="backend",
                    skill_slug="triage",
                ))
                await db.flush()
                publish(
                    f"agent_activity:{org.id}",
                    {"event_type": "skill_invoked", "status": "in_progress",
                     "skill_slug": "triage", "task_id": None,
                     "message": f"Triage '{payload.action}' started",
                     "actor_name": "triage", "repo_name": None,
                     "bud_number": None, "bud_title": None,
                     "impacted_repo_names": [], "created_at": ""},
                )

                bot_token = decrypt_secret(org.slack_bot_token or "")
                if not bot_token:
                    update_job(job_id, state=JobState.FAILED, error="No bot token configured")
                    return

                from app.services.slack_intake import (
                    continue_triage,
                    handle_pm_approval,
                    start_triage,
                )

                event_data = payload.event_data

                if payload.action == "start_triage":
                    from app.schemas.slack import SlackReactionEvent

                    event = SlackReactionEvent.model_validate(event_data)
                    await start_triage(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.item.channel,
                        message_ts=event.item.ts,
                        requester_slack_id=event.user,
                    )
                elif payload.action == "continue_triage":
                    from app.schemas.slack import SlackMessageEvent

                    event = SlackMessageEvent.model_validate(event_data)
                    await continue_triage(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.channel,
                        thread_ts=event.thread_ts or event.ts,
                        new_message=event.text,
                        sender_slack_id=event.user or "",
                    )
                elif payload.action == "pm_approval":
                    from app.schemas.slack import SlackReactionEvent

                    event = SlackReactionEvent.model_validate(event_data)
                    await handle_pm_approval(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.item.channel,
                        message_ts=event.item.ts,
                        approver_slack_id=event.user,
                        approved=payload.approved or False,
                    )

                # Log skill_completed
                db.add(AgentActivityLog(
                    org_id=org.id,
                    event_type="skill_completed",
                    status="completed",
                    message=f"Triage '{payload.action}' completed",
                    source="backend",
                    skill_slug="triage",
                ))
                await db.commit()
                publish(
                    f"agent_activity:{org.id}",
                    {"event_type": "skill_completed", "status": "completed",
                     "skill_slug": "triage", "task_id": None,
                     "message": f"Triage '{payload.action}' completed",
                     "actor_name": "triage", "repo_name": None,
                     "bud_number": None, "bud_title": None,
                     "impacted_repo_names": [], "created_at": ""},
                )
            except Exception:
                await db.rollback()
                # Log skill_failed in a fresh session
                if org is not None:
                    async with AsyncSessionLocal() as err_db:
                        err_db.add(AgentActivityLog(
                            org_id=org.id,
                            event_type="skill_failed",
                            status="failed",
                            message=f"Triage '{payload.action}' failed",
                            source="backend",
                            skill_slug="triage",
                        ))
                        await err_db.commit()
                    publish(
                        f"agent_activity:{org.id}",
                        {"event_type": "skill_failed", "status": "failed",
                         "skill_slug": "triage", "task_id": None,
                         "message": f"Triage '{payload.action}' failed",
                         "actor_name": "triage", "repo_name": None,
                         "bud_number": None, "bud_title": None,
                         "impacted_repo_names": [], "created_at": ""},
                    )
                raise

    update_job(job_id, state=JobState.COMPLETED, status_message="Done", progress_pct=100)
