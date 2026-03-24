"""In-memory presence cache for Slack user online/offline status.

Tracks presence state per (org_id, slack_user_id) pair.
No Redis needed — single-instance app, presence is ephemeral.

State machine:
  active  → Slack says online
  on_break → offline < 2hrs during work hours (8am–6pm)
  at_home  → offline >= 2hrs during work hours, or outside work hours
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.models.organization import Organization
from app.models.user import User
from app.services import slack_client

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


def get_presence_state(org_id: str, slack_user_id: str) -> str:
    """Compute tri-state presence: 'active', 'on_break', or 'at_home'.

    Returns 'active' when no data is available (graceful degradation).
    """
    key = (org_id, slack_user_id)
    entry = _cache.get(key)
    if not entry:
        return "active"

    return _compute_state(entry)


def get_all_states(org_id: str) -> dict[str, str]:
    """Return {slack_uid: state} for all cached users in an org."""
    result: dict[str, str] = {}
    for (oid, slack_uid), entry in _cache.items():
        if oid == org_id:
            result[slack_uid] = _compute_state(entry)
    return result


def _compute_state(entry: PresenceEntry) -> str:
    """Derive display state from raw presence entry."""
    if entry.status == "active":
        return "active"

    now = datetime.now(UTC)
    hour = now.hour
    is_work_hours = 8 <= hour < 18

    if is_work_hours and entry.went_offline_at:
        offline_duration = now - entry.went_offline_at
        if offline_duration < timedelta(hours=2):
            return "on_break"

    return "at_home"


async def refresh_all_presence(db: AsyncSession) -> None:
    """Poll Slack users.getPresence for all Slack-linked users.

    Iterates over organizations with a slack_bot_token, then queries
    all users with a slack_id and fetches their presence.
    """
    result = await db.execute(
        select(Organization.id, Organization.slack_bot_token).where(
            Organization.slack_bot_token.isnot(None)
        )
    )
    orgs = result.all()

    polled = 0
    errors = 0
    for org_id, encrypted_token in orgs:
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

        user_result = await db.execute(
            select(User.slack_id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == org_id,
                User.slack_id.isnot(None),
                User.is_active.is_(True),
            )
        )
        slack_ids = [row[0] for row in user_result.all() if row[0]]
        logger.debug(
            "presence_refresh_org",
            org_id=org_id_str,
            token_prefix=token_prefix,
            user_count=len(slack_ids),
        )

        for slack_uid in slack_ids:
            status = await slack_client.users_get_presence(token, slack_uid)
            if status:
                set_presence(org_id_str, slack_uid, status)
                polled += 1
            else:
                errors += 1

    logger.info(
        "presence_refresh_complete",
        users_polled=polled,
        errors=errors,
        orgs_checked=len(orgs),
    )
