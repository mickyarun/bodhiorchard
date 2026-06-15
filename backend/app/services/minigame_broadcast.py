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

"""High-score broadcast for the garden mini-games.

When a player dethrones the standing org-wide record for a game, DM every
Slack-linked member (except the breaker — they already know) a short
celebratory announcement.

Mirrors the best-effort DM pattern of ``minigame_nudge`` / ``race_invite``:
the org token is decrypted once, a DM is opened per user, and every Slack
call is best-effort so one bad token/DM never aborts the rest. No XP — pure
engagement.
"""

from __future__ import annotations

import uuid

import structlog

from app.config import settings
from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.repositories.minigame import LeaderboardRow
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.notifications import NotificationCategory, category_default
from app.services.slack_client import chat_post_message, conversations_open

logger = structlog.get_logger(__name__)


def is_new_org_record(*, prev_top: LeaderboardRow, breaker_id: uuid.UUID, score: int) -> bool:
    """True when ``score`` dethrones a DIFFERENT player's standing record.

    Pure (no I/O). The caller guarantees a prior record exists (a first-ever
    score isn't "breaking" one). A player padding their own lead is excluded —
    only taking the crown from someone else triggers a broadcast.
    """
    return prev_top.user_id != breaker_id and score > prev_top.best_score


def compose_high_score_announcement(
    *,
    breaker_name: str,
    game_name: str,
    score: int,
    previous_best: int,
    previous_holder: str,
    frontend_url: str,
) -> str:
    """Celebratory mrkdwn announcement for a new org record. Pure (no I/O)."""
    who = breaker_name.strip() or "Someone"
    holder = previous_holder.strip() or "the previous record"
    link = f"{frontend_url.rstrip('/')}/dashboard"
    return (
        "🏆 *New Garden Games record!*\n"
        f"*{who}* just topped *{game_name}* with *{score}* "
        f"— beating {holder}'s {previous_best}.\n"
        f"Think you can take it back? Play in the garden: {link}"
    )


async def broadcast_high_score(
    *,
    org_id: uuid.UUID,
    game_name: str,
    breaker_user_id: uuid.UUID,
    breaker_name: str,
    score: int,
    previous_best: int,
    previous_holder: str,
) -> int:
    """DM every Slack-linked member (except the breaker) the record news.

    Returns the number of messages actually sent. Skips silently when the org
    has no Slack token or no linked members; one failed DM never aborts the
    rest.
    """
    async with AsyncSessionLocal() as session:
        encrypted = await OrganizationRepository(session).get_slack_bot_token(org_id)
        if not encrypted:
            return 0
        token = decrypt_secret(encrypted)
        if not token:
            logger.warning("minigame_highscore_token_decrypt_failed", org_id=str(org_id))
            return 0
        pairs = await UserRepository(session).list_slack_recipients(
            org_id,
            category=NotificationCategory.MINIGAMES,
            default_enabled=category_default(NotificationCategory.MINIGAMES),
        )

    if not pairs:
        return 0

    message = compose_high_score_announcement(
        breaker_name=breaker_name,
        game_name=game_name,
        score=score,
        previous_best=previous_best,
        previous_holder=previous_holder,
        frontend_url=settings.frontend_url,
    )

    sent = 0
    for user_id, slack_id in pairs:
        if user_id == breaker_user_id:
            continue
        try:
            dm = await conversations_open(token, slack_id)
            if dm is None:
                continue
            result = await chat_post_message(token, dm, message)
            if result and result.get("ok"):
                sent += 1
        except Exception:
            logger.warning("minigame_highscore_send_failed", org_id=str(org_id), exc_info=True)

    if sent:
        logger.info(
            "minigame_highscore_broadcast",
            org_id=str(org_id),
            game=game_name,
            score=score,
            count=sent,
        )
    return sent
