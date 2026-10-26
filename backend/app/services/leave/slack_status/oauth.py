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
"""The one-click "let Bodhiorchard set my Slack status" approval.

The member starts it logged in; Slack sends their browser back to a
callback that has no login, so who it's for travels in a short-lived
signed ``state``. Its ``type`` keeps it from ever passing as a login
token (and a login token from passing as it).
"""

import contextlib
import time
import uuid
from dataclasses import dataclass
from typing import NoReturn
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.models.slack_status_link import SlackStatusLink
from app.repositories.slack_status_accounts import SlackStatusAccountRepository
from app.repositories.slack_status_link import SlackStatusLinkRepository
from app.repositories.user import UserRepository
from app.services.leave.slack_status.settings import StatusClient, redirect_url
from app.services.slack_self_link import link_own_account
from app.services.slack_user_api import (
    AUTHORIZE_URL,
    USER_SCOPES,
    SlackUserApiError,
    UserGrant,
    exchange_code,
    revoke,
)

STATE_TYPE = "slack_status_state"
STATE_TTL_SECONDS = 600


class InvalidStateError(Exception):
    """The state is forged, expired or for something else."""


def make_state(org_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Signed, 10-minute proof of who started the approval."""
    now = int(time.time())
    claims = {
        "type": STATE_TYPE,
        "org": str(org_id),
        "sub": str(user_id),
        "iat": now,
        "exp": now + STATE_TTL_SECONDS,
    }
    return jwt.encode(claims, settings.auth.secret_key, algorithm=settings.auth.algorithm)


def read_state(state: str) -> tuple[uuid.UUID, uuid.UUID]:
    """(org id, user id) from a state we signed; :class:`InvalidStateError` otherwise."""
    try:
        claims = jwt.decode(state, settings.auth.secret_key, algorithms=[settings.auth.algorithm])
        if claims.get("type") != STATE_TYPE:
            raise InvalidStateError
        return uuid.UUID(claims["org"]), uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidStateError from exc


def authorize_url(client: StatusClient, org_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Slack's approval page, asking only for the member's profile (status)."""
    query = {
        "client_id": client.client_id,
        "user_scope": USER_SCOPES,
        "redirect_uri": redirect_url(),
        "state": make_state(org_id, user_id),
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


class WrongSlackAccountError(Exception):
    """Approved from a Slack account that isn't the member's linked one."""


class UnlinkableSlackAccountError(WrongSlackAccountError):
    """The member had no link yet, and the account couldn't be shown to be theirs."""


@dataclass(frozen=True)
class Connected:
    """A kept connection: whether another org had the account, and tokens to hand back.

    The caller revokes ``stale_tokens`` only after committing, so a failed
    save never leaves the other org holding an already-revoked token.
    """

    moved: bool
    stale_tokens: list[str]


async def complete(
    db: AsyncSession, client: StatusClient, org_id: uuid.UUID, user_id: uuid.UUID, code: str
) -> Connected:
    """Exchange the code and keep the member's token (encrypted).

    Only for the member's own linked Slack account: otherwise someone could
    start the flow and get a colleague to approve it, and their leave would
    then show on the colleague's status. A member with no link yet gets
    this account linked if it's provably theirs (see ``slack_self_link``).

    A Slack account has one status, so one org drives it: if another org
    was, it's handed over here. Otherwise the two would overwrite and clear
    each other's status.
    """
    grant = await exchange_code(client.client_id, client.client_secret, code, redirect_url())
    member = await UserRepository(db).get_by_id_in_org(user_id, org_id)
    if member is None:
        await _refuse(db, grant, WrongSlackAccountError())
    if not member.slack_id and not await link_own_account(db, org_id, member, grant.slack_user_id):
        await _refuse(db, grant, UnlinkableSlackAccountError())
    if member.slack_id != grant.slack_user_id:
        await _refuse(db, grant, WrongSlackAccountError())
    accounts = SlackStatusAccountRepository(db)
    others = await accounts.links_elsewhere(grant.slack_user_id, org_id)
    await accounts.remove_elsewhere(grant.slack_user_id, org_id)
    await SlackStatusLinkRepository(db, org_id=org_id).save(
        user_id, grant.team_id, grant.slack_user_id, encrypt_secret(grant.token)
    )
    return Connected(moved=bool(others), stale_tokens=_stale(others, grant.token))


async def discard(db: AsyncSession, client: StatusClient, code: str) -> None:
    """Use up a code we won't keep, so it can't be finished from anywhere else
    (Slack doesn't tie a code to its state). Best effort."""
    with contextlib.suppress(SlackUserApiError, httpx.HTTPError):
        grant = await exchange_code(client.client_id, client.client_secret, code, redirect_url())
        await _hand_back_unless_held(db, grant)


async def _refuse(db: AsyncSession, grant: UserGrant, error: WrongSlackAccountError) -> NoReturn:
    """Hand the unused token back, then raise; best effort, as the member
    should still hear why."""
    with contextlib.suppress(SlackUserApiError, httpx.HTTPError):
        await _hand_back_unless_held(db, grant)
    raise error


async def _hand_back_unless_held(db: AsyncSession, grant: UserGrant) -> None:
    """Revoke the grant's token, unless a link holds it.

    Slack gives the same person the same token again, so if that account is
    already connected (say, from their other profile here) the token is in
    use, and handing it back would switch their status off.
    """
    links = await SlackStatusAccountRepository(db).links_for_account(grant.slack_user_id)
    if not any(decrypt_secret(link.token) == grant.token for link in links):
        await revoke(grant.token)


def _stale(others: list[SlackStatusLink], kept: str) -> list[str]:
    """The other orgs' tokens to revoke. Two orgs on one Slack app get the same
    token back for the same person: that one is the one we keep, never revoked."""
    tokens = {decrypt_secret(other.token) for other in others}
    return sorted(token for token in tokens if token and token != kept)
