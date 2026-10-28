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

"""A member linking their own Slack account, with no HR step.

The link says who clicks Approve in Slack (see :mod:`app.services.slack_identity`),
so it's only made when the account is provably the member's own:

- they signed in to Slack and approved as it (the OAuth grant names it; it
  can't be typed in or picked), and the connect was both started and finished
  in their own signed-in session;
- the org's own bot can see it, and Slack reports the same confirmed email
  as their profile here;
- nothing is taken over: they have no link yet, nobody here has that account,
  and they're in this org only (the link is shared across a person's orgs).

Anything else stays HR's job (Settings → Slack).
"""

import uuid
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.slack_identity import SlackIdentityRepository
from app.services.avatars import adopt_slack_photo, slack_photo_url
from app.services.slack_client import users_info
from app.services.slack_dm import bot_token

logger = structlog.get_logger(__name__)


async def link_own_account(
    db: AsyncSession, org_id: uuid.UUID, member: User, slack_user_id: str
) -> bool:
    """Link ``slack_user_id`` to ``member`` if it's provably theirs; True if linked.

    Only for a member with no link yet. Flushed with the caller's transaction.
    """
    if member.slack_id or not await _unclaimed(db, org_id, member.id, slack_user_id):
        return False
    profile = await _verified_profile(db, org_id, slack_user_id)
    # Lowercased only, as Settings → Slack matches emails: casefold would
    # also equate different non-ASCII addresses.
    slack_email = str(profile.get("email") or "").strip().lower()
    if not slack_email or slack_email != member.email.strip().lower():
        logger.info("slack_self_link_refused", org_id=str(org_id), user_id=str(member.id))
        return False
    member.slack_id = slack_user_id
    # The same photo a Slack import would bring in, never over an upload.
    # ``_unclaimed`` already confirmed this member is in this org alone.
    photo = slack_photo_url(profile)
    if photo:
        adopt_slack_photo(member, photo)
    await db.flush()
    logger.info(
        "slack_member_self_linked",
        org_id=str(org_id),
        user_id=str(member.id),
        slack_id=slack_user_id,
    )
    return True


async def _unclaimed(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, slack_user_id: str
) -> bool:
    """Nobody here has the account, and the member's link is theirs to set alone."""
    identities = SlackIdentityRepository(db)
    if await identities.membership_count(user_id) != 1:
        return False
    return not await identities.members_with_slack_id(org_id, slack_user_id)


async def _verified_profile(
    db: AsyncSession, org_id: uuid.UUID, slack_user_id: str
) -> dict[str, Any]:
    """The account's Slack profile if its email is confirmed; ``{}`` if it can't say."""
    token = await bot_token(db, org_id)
    if not token:
        return {}
    try:
        user = await users_info(token, slack_user_id)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("slack_self_link_lookup_failed", org_id=str(org_id), error=str(exc))
        return {}
    # A stranger is someone from another workspace (Slack Connect).
    if not user or user.get("deleted") or user.get("is_bot") or user.get("is_stranger"):
        return {}
    # An email the person never confirmed proves nothing.
    if user.get("is_email_confirmed") is False:
        return {}
    profile = user.get("profile")
    return profile if isinstance(profile, dict) else {}
