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

"""Job handler for Slack feature Q&A events.

Processes start_qa and continue_qa actions dispatched from the Slack
webhook via the async job queue.
"""

import asyncio
import re
from typing import Any

import structlog

from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.schemas.jobs import FeatureQAJobPayload, JobState
from app.services import slack_client
from app.services.agent_activity_logger import log_agent_activity
from app.services.job_queue import update_job
from app.services.job_utils import thread_locks
from app.services.slack_feature_qa import continue_feature_qa, start_feature_qa

logger = structlog.get_logger(__name__)

_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")


async def handle_feature_qa_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Process a Slack feature Q&A event (start or continue)."""
    payload = FeatureQAJobPayload(**raw_payload)
    update_job(job_id, status_message=f"Processing {payload.action}...", progress_pct=10)

    event_data = payload.event_data
    channel = event_data.get("channel", event_data.get("item", {}).get("channel", ""))
    # For app_mention: thread anchor is the message ts; for reactions: the item ts
    thread_ts = event_data.get("ts", event_data.get("item", {}).get("ts", ""))
    thread_key = f"{channel}:{thread_ts}"
    lock = thread_locks.setdefault(thread_key, asyncio.Lock())

    async with lock, AsyncSessionLocal() as db:
        org = None
        try:
            org = await OrganizationRepository(db).get_by_slack_team_id(payload.team_id)
            if org is None:
                update_job(
                    job_id,
                    state=JobState.FAILED,
                    error=f"Organization not found for team {payload.team_id}",
                )
                return

            await log_agent_activity(
                db,
                org_id=org.id,
                event_type="skill_invoked",
                skill_slug="feature-qa",
                message=f"Feature Q&A '{payload.action}' started",
            )

            bot_token = decrypt_secret(org.slack_bot_token or "")
            if not bot_token:
                update_job(job_id, state=JobState.FAILED, error="No bot token configured")
                return

            if payload.action == "start_qa":
                user_id = event_data.get("user", "")
                # Anchor the Q&A session to the PARENT thread when the trigger
                # message is itself a thread reply, so subsequent user replies
                # (which always carry the parent's thread_ts) route back here.
                if payload.event_type == "reaction_added":
                    messages = await slack_client.conversations_history(
                        bot_token, channel, latest=thread_ts, inclusive=True, limit=1
                    )
                    if messages:
                        raw_text = messages[0].get("text", "")
                        parent_ts = messages[0].get("thread_ts")
                        if parent_ts:
                            thread_ts = parent_ts
                    else:
                        raw_text = ""
                else:
                    raw_text = event_data.get("text", "")
                    parent_ts = event_data.get("thread_ts")
                    if parent_ts:
                        thread_ts = parent_ts
                question = _BOT_MENTION_RE.sub("", raw_text).strip()
                await start_feature_qa(
                    db=db,
                    org=org,
                    bot_token=bot_token,
                    channel=channel,
                    thread_ts=thread_ts,
                    requester_slack_user_id=user_id,
                    question_text=question,
                )

            elif payload.action == "continue_qa":
                user_reply = event_data.get("text", "")
                thread_ts_reply = event_data.get("thread_ts", thread_ts)
                await continue_feature_qa(
                    db=db,
                    org=org,
                    bot_token=bot_token,
                    channel=channel,
                    thread_ts=thread_ts_reply,
                    user_reply=user_reply,
                )

            await log_agent_activity(
                db,
                org_id=org.id,
                event_type="skill_completed",
                skill_slug="feature-qa",
                message=f"Feature Q&A '{payload.action}' completed",
            )
            await db.commit()
        except Exception:
            await db.rollback()
            if org is not None:
                await log_agent_activity(
                    None,
                    org_id=org.id,
                    event_type="skill_failed",
                    skill_slug="feature-qa",
                    message=f"Feature Q&A '{payload.action}' failed",
                )
            raise

    update_job(job_id, state=JobState.COMPLETED, status_message="Done", progress_pct=100)
