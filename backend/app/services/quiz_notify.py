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

"""Quiz notifications — best-effort Slack DMs + in-app event-bus signals.

Reuses the exact best-effort DM pattern from ``minigame_nudge``: org token
decrypted per send, DMs opened per user, every Slack call wrapped so one bad
token / user never aborts the rest. The low-queue nudge is in-app only (an
event-bus signal the admin review UI renders as a banner) so it never spams the
whole workspace.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from app.config import settings
from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.repositories.quiz_score import QuizScoreRepository
from app.repositories.user import UserRepository
from app.services.event_bus import publish
from app.services.org_settings import get_quiz_settings
from app.services.quiz_schedule_math import current_month_key
from app.services.slack_client import chat_post_message, conversations_open

logger = structlog.get_logger(__name__)


async def _dm_all_members(org_id: uuid.UUID, message: str, *, event: str) -> int:
    """DM ``message`` to every Slack-linked member of an org. Best-effort.

    Returns the number of DMs sent. Skips silently when the org has no Slack
    token or no linked members (the quiz is fully playable in-app regardless).
    """
    async with AsyncSessionLocal() as session:
        encrypted = await OrganizationRepository(session).get_slack_bot_token(org_id)
        if not encrypted:
            return 0
        token = decrypt_secret(encrypted)
        if not token:
            logger.warning("quiz_slack_token_decrypt_failed", org_id=str(org_id), quiz_event=event)
            return 0
        pairs = await UserRepository(session).list_active_slack_user_pairs(org_id)
        if not pairs:
            return 0

    sent = 0
    for _user_id, slack_id in pairs:
        try:
            dm = await conversations_open(token, slack_id)
            if dm is None:
                continue
            result = await chat_post_message(token, dm, message)
            if result and result.get("ok"):
                sent += 1
        except Exception:
            logger.warning(
                "quiz_slack_send_failed", org_id=str(org_id), quiz_event=event, exc_info=True
            )
    if sent:
        logger.info("quiz_slack_sent", org_id=str(org_id), quiz_event=event, count=sent)
    return sent


async def _month_standings(org_id: uuid.UUID, *, limit: int = 3) -> list[tuple[str, int]]:
    """Top (name, points) for the current month — drives the competitive copy."""
    async with AsyncSessionLocal() as db:
        period = current_month_key(datetime.now(UTC).date())
        rows = await QuizScoreRepository(db, org_id=org_id).leaderboard(
            period_month=period, limit=limit
        )
    return [(r.user_name, r.total_points) for r in rows]


def compose_open_message(link: str, standings: list[tuple[str, int]], sp_amount: float) -> str:
    """Build the quiz-open DM: SP prize + beat-the-leader nudge. Pure / testable."""
    lines = ["🧠 *Today's company quiz is live!* One question from your own dev data."]
    if sp_amount > 0:
        lines.append(
            f"🏅 *Rare SP up for grabs* — this month's top scorer wins *{sp_amount:g} SP*. "
            "SP is hard-earned, so every correct answer counts."
        )
    if standings and standings[0][1] > 0:
        leader, pts = standings[0]
        lines.append(f"🏆 *{leader}* leads with *{pts}* pts — can you top the board?")
    else:
        lines.append("🥇 The board's wide open — be the first to put points up this month!")
    lines.append(f"Answer before the window closes — the explanation drops at reveal.\n{link}")
    return "\n".join(lines)


def compose_reveal_message(link: str, standings: list[tuple[str, int]]) -> str:
    """Build the reveal DM showing who's topping the monthly board. Pure / testable."""
    lines = ["🎯 *The quiz answer is in* — see the explanation and how you did."]
    ranked = [(n, p) for n, p in standings if p > 0]
    if ranked:
        medals = ["🥇", "🥈", "🥉"]
        lines.append("*This month's leaders:*")
        lines += [
            f"{medals[i] if i < len(medals) else '•'} {name} — *{pts}*"
            for i, (name, pts) in enumerate(ranked)
        ]
    lines.append(link)
    return "\n".join(lines)


async def notify_quiz_open(org_id: uuid.UUID) -> int:
    """DM members that today's quiz is live — SP prize + beat-the-leader nudge."""
    link = f"{settings.frontend_url.rstrip('/')}/dashboard"
    standings = await _month_standings(org_id)
    async with AsyncSessionLocal() as db:
        config = await OrganizationRepository(db).get_config(org_id)
    sp_amount = get_quiz_settings(config).monthly_sp_amount
    return await _dm_all_members(
        org_id, compose_open_message(link, standings, sp_amount), event="quiz_open"
    )


async def notify_quiz_reveal(org_id: uuid.UUID) -> int:
    """DM members the answer is in, with the current monthly standings."""
    link = f"{settings.frontend_url.rstrip('/')}/dashboard"
    standings = await _month_standings(org_id)
    return await _dm_all_members(
        org_id, compose_reveal_message(link, standings), event="quiz_reveal"
    )


def nudge_low_queue(org_id: uuid.UUID, *, approved_remaining: int) -> None:
    """Signal (in-app) that the approved-question queue is running low.

    Published on the org quiz topic so the admin review UI can surface a banner;
    deliberately not a Slack broadcast, to avoid pinging the whole workspace.
    """
    publish(
        f"quiz:{org_id}",
        {"event_type": "low_queue", "approved_remaining": approved_remaining},
    )
    logger.info("quiz_low_queue_nudge", org_id=str(org_id), approved_remaining=approved_remaining)
