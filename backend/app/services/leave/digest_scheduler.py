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

"""Posts each org's daily who's-out message to Slack.

A 60-second tick, like the quiz scheduler: local times are recomputed every
pass, so it's DST-correct and catches up after a restart. The unique
(org, day) claim row makes it post at most once per day.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.models.leave_digest_post import DigestStatus
from app.repositories.leave_digest_post import LeaveDigestPostRepository
from app.repositories.organization import OrganizationRepository
from app.services.leave.digest_build import build_digest
from app.services.leave.digest_schedule import due_local_date
from app.services.leave.digest_settings import digest_settings, digest_zone
from app.services.slack_interactive import post_message

logger = structlog.get_logger(__name__)
TICK_SECONDS = 60


async def tick_once(now_utc: datetime | None = None) -> None:
    """One pass over every org with Slack connected."""
    now = now_utc or datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        orgs = await OrganizationRepository(db).list_with_slack_token_and_config()
    for org_id, encrypted_token, config in orgs:
        try:
            await _org_pass(org_id, encrypted_token, config, now)
        except Exception:
            logger.exception("leave_digest_org_failed", org_id=str(org_id))


async def _org_pass(
    org_id: uuid.UUID, encrypted_token: str, config: dict[str, Any] | None, now: datetime
) -> None:
    settings = digest_settings(config, org_id)
    if not settings.enabled or not settings.channel_id:
        return
    async with AsyncSessionLocal() as db:
        day = due_local_date(now, await digest_zone(db, org_id, settings), settings.post_time)
        if day is None:
            return
        posts = LeaveDigestPostRepository(db, org_id=org_id)
        if not await posts.claim(day):
            return
        await db.commit()
        try:
            text = await build_digest(db, org_id, day)
        except Exception:
            # Leave it retryable rather than stuck as "claimed".
            await db.rollback()
            await posts.finish(day, DigestStatus.FAILED, "build_failed")
            await db.commit()
            raise
        if text is None:
            await posts.finish(day, DigestStatus.SKIPPED, None)
            await db.commit()
            return
    token = decrypt_secret(encrypted_token)
    if token:
        _channel, _ts, error = await post_message(token, settings.channel_id, text)
    else:
        # Don't call Slack with an empty token; say why instead.
        error = "token_unreadable"
    async with AsyncSessionLocal() as db:
        status = DigestStatus.FAILED if error else DigestStatus.POSTED
        await LeaveDigestPostRepository(db, org_id=org_id).finish(day, status, error or None)
        await db.commit()
    if error:
        logger.warning("leave_digest_failed", org_id=str(org_id), day=day.isoformat(), error=error)
    else:
        logger.info("leave_digest_posted", org_id=str(org_id), day=day.isoformat())


async def run_forever() -> None:
    """Tick every minute until cancelled."""
    while True:
        try:
            await tick_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("leave_digest_tick_failed")
        await asyncio.sleep(TICK_SECONDS)
