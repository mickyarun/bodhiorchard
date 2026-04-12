"""In-memory presence cache for Slack user online/offline status.

Tracks presence state per (org_id, slack_user_id) pair.
No Redis needed — single-instance app, presence is ephemeral.

State machine:
  active  → Slack says online
  on_break → offline < 2hrs AND inside the org's configured working window
  at_home  → offline >= 2hrs, or outside working hours, or non-working day

The "configured working window" is sourced from per-org ``PresenceSettings``
(working days, working hours, timezone). When a caller does not (or cannot)
supply settings, the module falls back to the shipped ``PresenceSettings``
defaults — Mon-Fri, 08:00-18:00, no timezone (server-local). This preserves
the legacy hardcoded behaviour for callers that haven't been migrated.
"""

import asyncio
import zoneinfo
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.models.organization import Organization
from app.models.user import User
from app.schemas.settings import PresenceSettings
from app.services import slack_client
from app.services.colyseus_bridge import publish_to_colyseus
from app.services.org_settings import (
    DEFAULT_PRESENCE_SETTINGS,
    get_presence_settings,
)

# Maps Python's ``datetime.weekday()`` (0=Mon..6=Sun) to the lowercase
# 3-letter keys stored in ``PresenceSettings.working_days``.
_WEEKDAY_KEYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

logger = structlog.get_logger(__name__)


class PresenceEntry:
    """Cached presence state for a single Slack user."""

    __slots__ = ("status", "went_offline_at", "updated_at")

    def __init__(self, status: str) -> None:
        self.status = status
        self.went_offline_at: datetime | None = None if status == "active" else datetime.now(UTC)
        self.updated_at = datetime.now(UTC)


# Cache keyed by (org_id_str, slack_user_id)
_cache: dict[tuple[str, str], PresenceEntry] = {}


def set_presence(org_id: str, slack_user_id: str, status: str) -> None:
    """Update cached presence for a Slack user.

    Tracks went_offline_at on active→away transitions.
    """
    key = (org_id, slack_user_id)
    existing = _cache.get(key)

    if existing:
        if existing.status == "active" and status == "away":
            existing.went_offline_at = datetime.now(UTC)
        elif existing.status == "away" and status == "active":
            existing.went_offline_at = None
        existing.status = status
        existing.updated_at = datetime.now(UTC)
    else:
        _cache[key] = PresenceEntry(status)


def get_presence_state(
    org_id: str,
    slack_user_id: str,
    settings: PresenceSettings | None = None,
) -> str:
    """Compute tri-state presence: 'active', 'on_break', or 'at_home'.

    Returns 'active' when no data is available (graceful degradation).

    Args:
        org_id: The organization UUID as a string (cache key prefix).
        slack_user_id: The Slack user id (cache key suffix).
        settings: Per-org presence configuration (working days, hours,
            timezone). When ``None``, the shipped defaults are used,
            which preserves the legacy Mon-Fri / 08:00-18:00 / server-UTC
            behaviour for callers that haven't been migrated yet.
    """
    key = (org_id, slack_user_id)
    entry = _cache.get(key)
    if not entry:
        return "active"

    return _compute_state(entry, settings or DEFAULT_PRESENCE_SETTINGS)


def _compute_state(entry: PresenceEntry, settings: PresenceSettings) -> str:
    """Derive display state from a raw presence entry + org settings.

    Honours the org's configured working days, working hours, and
    timezone when deciding whether an offline user is ``on_break``
    (temporary gap inside work hours) or ``at_home`` (outside work
    hours, non-working day, or gap >= 2h).
    """
    if entry.status == "active":
        return "active"

    now_utc = datetime.now(UTC)

    # Resolve the "local now" the org cares about. When timezone is unset
    # (None), fall back to UTC — that matches what this function did
    # before it became timezone-aware, preserving behaviour for every
    # un-migrated org.
    if settings.timezone is not None:
        tz = zoneinfo.ZoneInfo(settings.timezone)
        local_now = now_utc.astimezone(tz)
    else:
        local_now = now_utc

    local_dow_key = _WEEKDAY_KEYS[local_now.weekday()]
    is_working_day = local_dow_key in settings.working_days

    # Lexicographic "HH:MM" comparison works because of zero-padding;
    # no need to parse into integers.
    local_hhmm = local_now.strftime("%H:%M")
    in_work_hours = (
        is_working_day
        and settings.working_hours_start <= local_hhmm < settings.working_hours_end
    )

    if in_work_hours and entry.went_offline_at:
        offline_duration = now_utc - entry.went_offline_at
        if offline_duration < timedelta(hours=2):
            return "on_break"

    return "at_home"


async def refresh_all_presence(db: AsyncSession) -> None:
    """Poll Slack users.getPresence for all Slack-linked users.

    Iterates over organizations with a slack_bot_token, then queries
    all users with a slack_id and fetches their presence.
    """
    result = await db.execute(
        select(
            Organization.id,
            Organization.slack_bot_token,
            Organization.config,
        ).where(Organization.slack_bot_token.isnot(None))
    )
    orgs = result.all()

    polled = 0
    errors = 0
    for org_id, encrypted_token, org_config in orgs:
        # Resolve per-org presence settings once per org, outside the
        # per-user loop. Defaults apply if the org has no "presence" key.
        settings = get_presence_settings(org_config)
        token = decrypt_secret(encrypted_token or "")
        if not token:
            logger.warning(
                "presence_refresh_skip_org",
                org_id=str(org_id),
                reason="empty token after decryption",
                stored_prefix=(encrypted_token or "")[:15] + "...",
            )
            continue

        # Log token shape for debugging (e.g. "xoxb-12..." vs garbage)
        token_prefix = token[:10] + "..." if len(token) > 10 else "***"
        org_id_str = str(org_id)

        # Validate token once per org before polling all users
        auth_info = await slack_client.auth_test(token)
        if not auth_info:
            logger.error(
                "presence_refresh_token_invalid",
                org_id=org_id_str,
                token_prefix=token_prefix,
                action="Slack bot token is revoked or expired — re-enter in Settings",
            )
            continue
        logger.debug(
            "presence_refresh_token_ok",
            org_id=org_id_str,
            team=auth_info.get("team"),
            bot_user=auth_info.get("user"),
        )

        from app.models.user import OrgToUser

        # Batch fetch (user_id, slack_id) pairs in one query. We need the
        # user_id alongside the slack_id so we can publish presence
        # transitions to Colyseus keyed by the app's canonical user_id,
        # not the Slack-side ID. Batching avoids an N+1 lookup during
        # the per-user polling loop below.
        user_result = await db.execute(
            select(User.id, User.slack_id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id.isnot(None),
                User.is_active.is_(True),
            )
        )
        # Keep as a list of (user_id, slack_id) tuples so we can iterate once
        # and still have both IDs available for the publish.
        user_slack_pairs = [
            (user_id, slack_id)
            for user_id, slack_id in user_result.all()
            if slack_id
        ]
        logger.debug(
            "presence_refresh_org",
            org_id=org_id_str,
            token_prefix=token_prefix,
            user_count=len(user_slack_pairs),
        )

        for user_id, slack_uid in user_slack_pairs:
            status = await slack_client.users_get_presence(token, slack_uid)
            if not status:
                errors += 1
                continue

            # Capture the display state BEFORE the cache update so we can
            # detect tri-state transitions (active / on_break / at_home).
            # The raw Slack status is binary (active/away), but the display
            # state is derived — e.g. "away" + recent → on_break, "away" +
            # old → at_home. We only publish when the display state changes,
            # not every time the raw status is the same.
            old_display = get_presence_state(org_id_str, slack_uid, settings)
            set_presence(org_id_str, slack_uid, status)
            new_display = get_presence_state(org_id_str, slack_uid, settings)
            polled += 1

            if old_display != new_display:
                # Fire-and-forget publish to Colyseus. publish_to_colyseus has
                # a 2s internal timeout and swallows errors, so we don't need
                # to await it — a slow or down Colyseus server must not stall
                # the Slack polling loop.
                asyncio.create_task(
                    publish_to_colyseus(
                        str(org_id),
                        "member_presence",
                        {
                            "user_id": str(user_id),
                            "presence": new_display,
                        },
                    )
                )
                logger.info(
                    "presence_transition",
                    org_id=org_id_str,
                    user_id=str(user_id),
                    old=old_display,
                    new=new_display,
                )

    logger.info(
        "presence_refresh_complete",
        users_polled=polled,
        errors=errors,
        orgs_checked=len(orgs),
    )
