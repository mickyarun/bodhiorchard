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

"""Daily Slack nudge for the garden mini-games.

Per org, DMs each Slack-linked member a short digest:
  - "keep your N-day streak alive" for any game whose streak is live
    (last played today/yesterday) but NOT yet played today
  - "Alice leads Fishing with 48 — beat it?" leaderboard nudge for games
    where someone else is ahead (or no one has played yet)

Mirrors the best-effort Slack pattern in ``race_invite_service``: org
token decrypted per send, DMs opened per user, every Slack call fails
silently so one bad token never aborts the sweep. Reuses the existing
``slack_client`` seam. No XP, no in-app notification — a pure nudge.

Scheduling reuses the daily-loop skeleton from
``velocity_snapshot_roller`` / ``mcp_audit_cleanup``: one in-process
asyncio task registered in ``main.py`` lifespan.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import structlog

from app.config import settings
from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.repositories.minigame import LeaderboardRow, MinigameRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.minigame_service import GAMES
from app.services.slack_client import chat_post_message, conversations_open

logger = structlog.get_logger(__name__)

SLEEP_SECONDS = 24 * 60 * 60
RETRY_SLEEP_SECONDS = 60 * 60
ALERT_AFTER_CONSECUTIVE_FAILURES = 2


@dataclass(slots=True, frozen=True)
class _UserGameState:
    game: str
    best_score: int
    current_streak: int
    last_played_date: date | None


def compose_digest(
    *,
    user_id: uuid.UUID,
    user_name: str,
    states: list[_UserGameState],
    leaders: dict[str, LeaderboardRow | None],
    today: date,
    frontend_url: str,
) -> str | None:
    """Build one user's nudge (mrkdwn), or None when there's nothing to say.

    Pure function — no I/O — so the nudge logic is unit-testable in isolation.
    """
    by_game = {s.game: s for s in states}
    lines: list[str] = []

    for key, spec in GAMES.items():
        st = by_game.get(key)
        leader = leaders.get(key)

        # Streak-at-risk: a live streak last continued YESTERDAY (so it's
        # still alive) but not yet played today.
        if (
            st
            and st.last_played_date == today - timedelta(days=1)
            and st.current_streak >= 1
        ):
            lines.append(
                f"🔥 Play *{spec.name}* today to keep your "
                f"*{st.current_streak}-day* streak alive."
            )
            continue

        # Leaderboard nudge: someone else leads, or nobody has played yet.
        if leader is None:
            lines.append(f"🌱 No one's played *{spec.name}* yet — claim the top spot!")
        elif leader.user_id != user_id:
            mine = st.best_score if st else 0
            lines.append(
                f"🏆 *{leader.user_name}* leads *{spec.name}* with "
                f"*{leader.best_score}*"
                + (f" — your best is {mine}. Beat it?" if mine else " — can you top it?")
            )

    if not lines:
        return None

    link = f"{frontend_url.rstrip('/')}/dashboard"
    first = user_name.split()[0] if user_name.strip() else None
    header = (
        f"🎮 *Garden Games* — hey {first}!"
        if first
        else "🎮 *Garden Games* — your daily nudge"
    )
    footer = f"Play in the garden: {link}"
    return "\n".join([header, *lines, footer])


async def send_org_nudges(org_id: uuid.UUID) -> int:
    """Compose + DM a nudge to every Slack-linked member of one org.

    Returns the number of messages actually sent. Skips silently when the
    org has no Slack token or no linked members.
    """
    async with AsyncSessionLocal() as session:
        encrypted = await OrganizationRepository(session).get_slack_bot_token(org_id)
        if not encrypted:
            return 0
        token = decrypt_secret(encrypted)
        if not token:
            logger.warning("minigame_nudge_token_decrypt_failed", org_id=str(org_id))
            return 0

        pairs = await UserRepository(session).list_active_slack_user_pairs(org_id)
        if not pairs:
            return 0

        repo = MinigameRepository(session, org_id=org_id)
        # One leaderboard fetch per game, shared across all users.
        leaders: dict[str, LeaderboardRow | None] = {}
        for key in GAMES:
            top = await repo.leaderboard(game=key, limit=1)
            leaders[key] = top[0] if top else None

        today = datetime.now(UTC).date()
        # Resolve display names once.
        user_repo = UserRepository(session)
        digests: list[tuple[str, str]] = []  # (slack_id, message)
        for user_id, slack_id in pairs:
            rows = await repo.list_for_user(user_id)
            states = [
                _UserGameState(
                    game=r.game,
                    best_score=r.best_score,
                    current_streak=r.current_streak,
                    last_played_date=r.last_played_date,
                )
                for r in rows
            ]
            user = await user_repo.get_by_id_in_org(user_id, org_id)
            message = compose_digest(
                user_id=user_id,
                user_name=user.name if user else "",
                states=states,
                leaders=leaders,
                today=today,
                frontend_url=settings.frontend_url,
            )
            if message:
                digests.append((slack_id, message))

    # Slack I/O outside the DB session — best-effort, isolated per user.
    sent = 0
    for slack_id, message in digests:
        try:
            dm = await conversations_open(token, slack_id)
            if dm is None:
                continue
            result = await chat_post_message(token, dm, message)
            if result and result.get("ok"):
                sent += 1
        except Exception:
            logger.warning("minigame_nudge_send_failed", org_id=str(org_id), exc_info=True)
    if sent:
        logger.info("minigame_nudge_sent", org_id=str(org_id), count=sent)
    return sent


async def sweep_once() -> int:
    """Nudge every org once. Returns total messages sent across orgs."""
    async with AsyncSessionLocal() as session:
        org_ids = await OrganizationRepository(session).list_all_ids()

    total = 0
    for oid in org_ids:
        try:
            total += await send_org_nudges(oid)
        except Exception:
            logger.warning("minigame_nudge_org_failed", org_id=str(oid), exc_info=True)
    return total


async def run_forever() -> None:
    """Daily loop — same structure as velocity_snapshot_roller.run_forever."""
    consecutive_failures = 0
    while True:
        try:
            await sweep_once()
            consecutive_failures = 0
            sleep_for = SLEEP_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_failures += 1
            log = (
                logger.error
                if consecutive_failures >= ALERT_AFTER_CONSECUTIVE_FAILURES
                else logger.exception
            )
            log("minigame_nudge_failed", consecutive_failures=consecutive_failures)
            sleep_for = RETRY_SLEEP_SECONDS
        await asyncio.sleep(sleep_for)
