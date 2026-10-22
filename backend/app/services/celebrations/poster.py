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

"""Assemble and send one org's celebration digest — and the settings-page sample.

Delivery rules, in the order :func:`post_digest` applies them:

1. Everything that can fail for a *fixable* reason (no channel, nobody to
   celebrate, no Slack token, a token that will not decrypt) is checked
   while the date is still unclaimed, so fixing it later the same morning
   still gets the post out.
2. The date is claimed **before** the Slack call. A crash mid-send then
   loses a day instead of re-posting to the whole channel every minute.
3. A Slack call that *definitely* did not deliver is marked FAILED and
   retried up to :data:`MAX_ATTEMPTS` times, :data:`RETRY_DELAY` apart,
   inside the post window. A call that *might* have delivered (read
   timeout) is marked UNKNOWN and never retried.
4. If Slack rejects the blocks — typically because it could not fetch an
   avatar or the GIF — the same attempt is re-sent text-only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy.exc import IntegrityError

from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.models.celebration_post import CelebrationPostStatus
from app.repositories.celebration_post import CelebrationPostRepository
from app.repositories.employee_profile import Celebrant, EmployeeProfileRepository
from app.repositories.organization import OrganizationRepository
from app.schemas.settings import CelebrationSettings
from app.services.celebrations.compose import compose_digest, fallback_text
from app.services.celebrations.gif import random_celebration_gif
from app.services.celebrations.schedule import MAX_SPAN_DAYS, PostWindow
from app.services.slack_client import PostOutcome, post_message_outcome

logger = structlog.get_logger(__name__)

# First attempt plus two retries.
MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(minutes=10)

# Slack's code when it refuses a Block Kit payload — including when it
# cannot download an image accessory or image block.
_BLOCKS_REJECTED = "invalid_blocks"


@dataclass(frozen=True)
class PostResult:
    """What one ``post_digest`` / ``post_sample`` call did."""

    posted: bool
    birthdays: int = 0
    anniversaries: int = 0
    reason: str | None = None


async def _resolve_token(org_id: uuid.UUID) -> tuple[str | None, str | None]:
    """``(token, None)`` or ``(None, reason)`` — never raises."""
    async with AsyncSessionLocal() as db:
        encrypted = await OrganizationRepository(db).get_slack_bot_token(org_id)
    if not encrypted:
        logger.warning("celebration_no_slack_token", org_id=str(org_id))
        return None, "no_slack_token"
    try:
        return decrypt_secret(encrypted), None
    except Exception:
        logger.warning("celebration_token_decrypt_failed", org_id=str(org_id))
        return None, "token_decrypt_failed"


async def _send(
    token: str,
    channel: str,
    birthdays: list[Celebrant],
    anniversaries: list[Celebrant],
    settings: CelebrationSettings,
    *,
    sample: bool = False,
) -> PostOutcome:
    """One delivery attempt, with a text-only resend if Slack rejects images."""
    gif_url = (
        await random_celebration_gif(tags=settings.gif_tags, rating=settings.gif_rating)
        if settings.gif_enabled
        else None
    )
    text = fallback_text(birthdays, anniversaries)
    outcome = await post_message_outcome(
        token,
        channel,
        text,
        blocks=compose_digest(
            birthdays,
            anniversaries,
            gif_url=gif_url,
            mention_channel=settings.mention_channel,
            sample=sample,
        ),
    )
    if outcome.ok or outcome.error != _BLOCKS_REJECTED:
        return outcome

    # ``invalid_blocks`` means Slack refused the whole payload without
    # posting anything, so resending is safe. Dropping the images removes
    # the usual cause: an avatar or GIF URL Slack's servers cannot fetch.
    logger.warning("celebration_blocks_rejected_retrying_text_only", channel=channel)
    return await post_message_outcome(
        token,
        channel,
        text,
        blocks=compose_digest(
            birthdays,
            anniversaries,
            mention_channel=settings.mention_channel,
            include_images=False,
            sample=sample,
        ),
    )


def _status_for(outcome: PostOutcome) -> CelebrationPostStatus:
    if outcome.ok:
        return CelebrationPostStatus.SENT
    if outcome.maybe_delivered:
        return CelebrationPostStatus.UNKNOWN
    return CelebrationPostStatus.FAILED


async def post_digest(
    org_id: uuid.UUID,
    settings: CelebrationSettings,
    window: PostWindow,
    *,
    now_utc: datetime | None = None,
) -> PostResult:
    """Post (or retry) the digest for ``window`` to the org's celebration channel.

    Args:
        org_id: Tenant to post for.
        settings: That org's resolved celebration settings.
        window: The date and coverage this digest announces.
        now_utc: Clock override for tests.

    Returns:
        A :class:`PostResult`; ``posted=False`` with a ``reason`` for every
        no-op or failure path.
    """
    channel = settings.slack_channel_id
    if not channel:
        return PostResult(posted=False, reason="no_channel")
    now = now_utc or datetime.now(UTC)

    async with AsyncSessionLocal() as db:
        ledger = CelebrationPostRepository(db, org_id=org_id)
        existing = await ledger.get_for_date(window.post_date)

        occasions: list[date]
        if existing is not None:
            if existing.status != CelebrationPostStatus.FAILED:
                return PostResult(posted=False, reason="already_posted")
            if existing.attempts >= MAX_ATTEMPTS:
                return PostResult(posted=False, reason="retries_exhausted")
            if existing.updated_at and now - existing.updated_at < RETRY_DELAY:
                return PostResult(posted=False, reason="retry_pending")
            # A retry re-announces exactly what the failed attempt meant to.
            occasions = list(existing.covered_dates)
        else:
            elsewhere = await ledger.dates_announced_near(
                window.post_date, span_days=MAX_SPAN_DAYS
            )
            occasions = [d for d in window.occasions if d not in elsewhere]

        birthdays, anniversaries = await EmployeeProfileRepository(
            db, org_id=org_id
        ).list_celebrants(
            occasions,
            birthdays=settings.include_birthdays,
            anniversaries=settings.include_anniversaries,
        )
        if not birthdays and not anniversaries:
            # Deliberately NOT claimed: leaving the date open costs one cheap
            # query per tick and lets a birth date entered at 09:45 still be
            # announced inside the post window.
            return PostResult(posted=False, reason="nobody")

    # Fixable failures are resolved before the claim (rule 1).
    token, token_problem = await _resolve_token(org_id)
    if token is None:
        return PostResult(posted=False, reason=token_problem)

    async with AsyncSessionLocal() as db:
        ledger = CelebrationPostRepository(db, org_id=org_id)
        try:
            if existing is not None:
                won = await ledger.claim_retry(existing, slack_channel_id=channel)
                if not won:
                    await db.rollback()
                    return PostResult(posted=False, reason="already_posted")
                row_id = existing.id
            else:
                row = await ledger.claim(
                    window.post_date,
                    slack_channel_id=channel,
                    covered_dates=occasions,
                    birthday_count=len(birthdays),
                    anniversary_count=len(anniversaries),
                )
                row_id = row.id
            await db.commit()
        except IntegrityError:
            await db.rollback()
            # Another instance won the race for this date.
            return PostResult(posted=False, reason="already_posted")

    try:
        outcome = await _send(token, channel, birthdays, anniversaries, settings)
    except Exception as exc:
        # ``post_message_outcome`` never raises, so this is a bug in our own
        # composition. Nothing was sent; record it so the retry path sees it.
        logger.exception("celebration_send_crashed", org_id=str(org_id))
        outcome = PostOutcome(ok=False, error=f"internal:{type(exc).__name__}")

    status = _status_for(outcome)
    async with AsyncSessionLocal() as db:
        await CelebrationPostRepository(db, org_id=org_id).record_outcome(
            row_id, status=status, message_ts=outcome.ts, error=outcome.error
        )
        await db.commit()

    log_fields = {
        "org_id": str(org_id),
        "channel": channel,
        "celebrate_date": window.post_date.isoformat(),
        "birthdays": len(birthdays),
        "anniversaries": len(anniversaries),
    }
    if not outcome.ok:
        # ERROR, not WARNING: this is someone's birthday going unannounced.
        logger.error(
            "celebration_post_failed", status=status.value, error=outcome.error, **log_fields
        )
        return PostResult(posted=False, reason=f"slack:{outcome.error}")

    logger.info("celebration_posted", **log_fields)
    return PostResult(posted=True, birthdays=len(birthdays), anniversaries=len(anniversaries))


async def post_sample(
    org_id: uuid.UUID,
    settings: CelebrationSettings,
    *,
    actor_name: str,
    actor_slack_id: str | None,
    actor_avatar_url: str | None,
    today: date,
) -> PostResult:
    """Post a clearly-labelled sample digest, with the admin as the celebrant.

    Lets whoever configures the feature check the channel, the bot's
    membership, avatars and the GIF on any day — including days with
    nobody to celebrate — without touching the ledger. A real
    announcement is never consumed or sent early by testing.
    """
    channel = settings.slack_channel_id
    if not channel:
        return PostResult(posted=False, reason="no_channel")
    token, token_problem = await _resolve_token(org_id)
    if token is None:
        return PostResult(posted=False, reason=token_problem)

    sample_person = Celebrant(
        user_id=uuid.uuid4(),
        name=actor_name,
        avatar_url=actor_avatar_url,
        slack_id=actor_slack_id,
        month=today.month,
        day=today.day,
    )
    outcome = await _send(token, channel, [sample_person], [], settings, sample=True)
    if not outcome.ok:
        return PostResult(posted=False, reason=f"slack:{outcome.error}")
    return PostResult(posted=True, birthdays=1)
