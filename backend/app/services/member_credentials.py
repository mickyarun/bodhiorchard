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
"""Sign-in passwords: someone's own, and temporary ones set for them.

Shared by the Members page (admins) and an employee's record (HR). The
caller has already checked they may take over the person's identity
(:func:`app.services.identity_takeover.assert_can_act_as`): a temporary
password lets whoever sees it sign in as them until it's changed.
"""

import secrets
import string
from datetime import UTC, datetime

import httpx
import structlog

from app.config import settings
from app.core.encryption import decrypt_secret
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User
from app.services.slack_client import chat_post_message, conversations_open

logger = structlog.get_logger(__name__)

_ALPHABET = string.ascii_letters + string.digits + "!@#$%&*"


def generate_password(length: int = 12) -> str:
    """A random password with a lower, an upper, a digit and a symbol."""
    while True:
        password = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%&*" for c in password)
        ):
            return password


def login_url() -> str:
    """Where the person signs in."""
    return settings.frontend_url.rstrip("/") + "/login"


def has_own_password(user: User) -> bool:
    """True once they've chosen a password, or signed in with one that wasn't temporary."""
    return user.password_set_at is not None


def note_own_password(user: User) -> None:
    """They signed in (or refreshed a session) with a password of their own: remember it.

    A temporary password doesn't count: they still have to choose one.
    """
    if user.password_set_at is None and not user.must_change_password:
        user.password_set_at = datetime.now(UTC)


def chose_password(user: User, password: str) -> None:
    """They set their own password (changing it, or creating the org)."""
    user.password_hash = hash_password(password)
    user.must_change_password = False
    user.password_set_at = datetime.now(UTC)


def set_temporary_password(user: User) -> str:
    """Give ``user`` a new temporary password they must change at sign-in; returns it."""
    password = generate_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.password_set_at = None
    return password


async def send_credentials_slack(
    org: Organization, user: User, password: str
) -> tuple[bool, str | None]:
    """DM ``user`` their sign-in details; (sent, reason it wasn't)."""
    if not user.slack_id:
        return False, "This member has no linked Slack account."
    if not org.slack_bot_token:
        return False, "Slack is not configured for this organization."
    bot_token = decrypt_secret(org.slack_bot_token)
    if not bot_token:
        return False, "Slack token decryption failed. Check your encryption key."
    message = (
        f"Hi {user.name}! Your login credentials have been set up.\n\n"
        f"*Email:* `{user.email}`\n"
        f"*Temporary Password:* `{password}`\n\n"
        f"Log in here: {login_url()}\n"
        f"You will be asked to change your password on first login."
    )
    # Never raises: the password is already changed, so the caller must
    # still get it back to share some other way.
    try:
        dm_channel = await conversations_open(bot_token, user.slack_id)
        if not dm_channel:
            return False, "Failed to open DM channel with this member."
        posted = await chat_post_message(bot_token, dm_channel, message)
    except (httpx.HTTPError, ValueError):
        logger.warning("credentials_slack_failed", user_id=str(user.id), exc_info=True)
        return False, "Failed to send Slack DM."
    if posted is None:
        return False, "Failed to send Slack DM."
    logger.info("credentials_sent_via_slack", user_id=str(user.id))
    return True, None
