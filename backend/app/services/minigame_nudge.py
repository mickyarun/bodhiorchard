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

Scheduling: one in-process asyncio task (registered in ``main.py``
lifespan) ticks every 15 minutes and sends each org its nudge at
**09:00 in that org's own timezone** — the IANA zone from the org's
presence settings (``organizations.config.presence.timezone``). Orgs
with no zone set fall back to the server's local time, matching the
presence systems' own default. A per-process ``{org_id: local-date}``
map dedupes so each org is nudged at most once per local day; only the
*scheduling* is timezone-aware — streak bookkeeping stays UTC, exactly
as plays are recorded (``minigame_service``).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.config import settings
from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.repositories.minigame import LeaderboardRow, MinigameRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.minigame_service import GAMES
from app.services.notifications import NotificationCategory, category_default
from app.services.org_settings import get_presence_settings
from app.services.slack_client import chat_post_message, conversations_open

logger = structlog.get_logger(__name__)

# Send at 09:00 in each org's local zone; tick often enough to land inside
# the 09:00 hour without an external scheduler.
NUDGE_HOUR_LOCAL = 9
TICK_SECONDS = 15 * 60
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
        if st and st.last_played_date == today - timedelta(days=1) and st.current_streak >= 1:
            lines.append(
                f"🔥 Play *{spec.name}* today to keep your *{st.current_streak}-day* streak alive."
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
        f"🎮 *Garden Games* — hey {first}!" if first else "🎮 *Garden Games* — your daily nudge"
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

        pairs = await UserRepository(session).list_slack_recipients(
            org_id,
            category=NotificationCategory.MINIGAMES,
            default_enabled=category_default(NotificationCategory.MINIGAMES),
        )
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


def _zone_for_config(config: dict[str, Any] | None) -> ZoneInfo | None:
    """Resolve an org's presence IANA zone, or None for server-local time.

    ``None`` (no zone configured, or an unresolvable name) maps to the
    server's local zone — the same fallback the presence systems use.
    """
    tz = get_presence_settings(config).timezone
    if not tz:
        return None
    try:
        return ZoneInfo(tz)
    except Exception:
        return None


def _due_local_date(
    *,
    config: dict[str, Any] | None,
    now_utc: datetime,
    last_nudged_local: date | None,
) -> date | None:
    """The org-local date to stamp if a nudge is due right now, else None.

    Pure (no I/O) so the schedule decision is unit-testable. Due means it
    is the 09:00 hour in the org's zone and we have not already nudged on
    that local date.
    """
    now_local = now_utc.astimezone(_zone_for_config(config))
    if now_local.hour != NUDGE_HOUR_LOCAL:
        return None
    if last_nudged_local == now_local.date():
        return None
    return now_local.date()


async def _tick(now_utc: datetime, sent_on: dict[uuid.UUID, date]) -> int:
    """One scheduler pass: nudge every org whose local 09:00 has arrived.

    ``sent_on`` is mutated in place to record the local date each org was
    nudged, so a later tick in the same hour does not re-send. A failed
    send is left unrecorded so the next tick retries within the hour.
    """
    async with AsyncSessionLocal() as session:
        orgs = await OrganizationRepository(session).list_with_slack_token_and_config()

    total = 0
    for org_id, _token, config in orgs:
        due = _due_local_date(
            config=config, now_utc=now_utc, last_nudged_local=sent_on.get(org_id)
        )
        if due is None:
            continue
        try:
            total += await send_org_nudges(org_id)
            sent_on[org_id] = due
        except Exception:
            logger.warning("minigame_nudge_org_failed", org_id=str(org_id), exc_info=True)
    return total


async def run_forever() -> None:
    """Ticking loop — wakes every 15 min and sends at each org's local 09:00."""
    sent_on: dict[uuid.UUID, date] = {}
    consecutive_failures = 0
    while True:
        try:
            await _tick(datetime.now(UTC), sent_on)
            consecutive_failures = 0
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
        await asyncio.sleep(TICK_SECONDS)
