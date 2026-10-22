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

"""Slack status on WFH and leave days: HR's settings and each member's own link."""

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.slack_status_link import SlackStatusLinkRepository
from app.schemas.leave_slack_status import (
    ConnectOutcome,
    SlackStatusConnect,
    SlackStatusFinish,
    SlackStatusFinished,
    SlackStatusMine,
    SlackStatusSettings,
    SlackStatusUpdate,
)
from app.services.background import spawn
from app.services.leave.permissions import CONFIGURE
from app.services.leave.slack_status.apply import forget, hand_back, refresh_member
from app.services.leave.slack_status.oauth import (
    InvalidStateError,
    UnlinkableSlackAccountError,
    WrongSlackAccountError,
    authorize_url,
    complete,
    discard,
    read_state,
)
from app.services.leave.slack_status.scheduler import clear_all
from app.services.leave.slack_status.settings import load_client, load_settings, save_settings
from app.services.slack_user_api import SlackUserApiError

router = APIRouter(tags=["leave"])
logger = structlog.get_logger(__name__)


@router.get("/slack-status", response_model=SlackStatusSettings)
async def get_slack_status_settings(
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> SlackStatusSettings:
    """The Slack app's client for status (never the secret)."""
    return await load_settings(db, current_user.org_id)


@router.put("/slack-status", response_model=SlackStatusSettings)
async def put_slack_status_settings(
    body: SlackStatusUpdate,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> SlackStatusSettings:
    """Save the Slack app's client id / secret and switch status on or off.

    Switching off takes our status off everyone straight away.
    """
    was_on = (await load_client(db, current_user.org_id)).enabled
    saved = await save_settings(db, current_user.org_id, body)
    await db.commit()
    if was_on and not saved.enabled:
        spawn(clear_all(current_user.org_id))
    return saved


@router.get("/slack-status/me", response_model=SlackStatusMine)
async def get_my_slack_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SlackStatusMine:
    """Whether status is offered here, and whether the caller has connected."""
    client = await load_client(db, current_user.org_id)
    link = await SlackStatusLinkRepository(db, org_id=current_user.org_id).for_user(
        current_user.id
    )
    return SlackStatusMine(
        available=client.ready, connected=link is not None, linked=bool(current_user.slack_id)
    )


@router.post("/slack-status/me/connect", response_model=SlackStatusConnect)
async def connect_my_slack_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SlackStatusConnect:
    """Where to send the caller to approve in Slack."""
    client = await load_client(db, current_user.org_id)
    if not client.ready:
        raise HTTPException(status_code=409, detail="Slack status isn't set up for your team.")
    return SlackStatusConnect(url=authorize_url(client, current_user.org_id, current_user.id))


@router.post("/slack-status/me/finish", response_model=SlackStatusFinished)
async def finish_my_slack_status(
    body: SlackStatusFinish,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SlackStatusFinished:
    """Finish what Slack sent back: keep the token, set today's status.

    Only for the member who started it, checked before the code is kept, so
    a connect link opened by anyone else changes nothing.
    """
    try:
        org_id, user_id = read_state(body.state)
    except InvalidStateError:
        return SlackStatusFinished(outcome="expired")
    if user_id == current_user.id and org_id != current_user.org_id:
        # Theirs, started in their other organization: left for them to finish there.
        return SlackStatusFinished(outcome="other_org")
    # The client the code was issued for (the state's org), to use it up if refused.
    client = await load_client(db, org_id)
    if user_id != current_user.id:
        # Used up, never kept: whoever approved can't have it finished elsewhere.
        if client.ready:
            await discard(db, client, body.code)
        return SlackStatusFinished(outcome="not_yours")
    if not client.ready:
        return SlackStatusFinished(outcome="failed")
    outcome: ConnectOutcome
    try:
        connected = await complete(db, client, org_id, user_id, body.code)
    except UnlinkableSlackAccountError:
        outcome = "unlinkable"
    except WrongSlackAccountError:
        outcome = "wrong_account"
    except SlackUserApiError as exc:
        logger.warning("slack_status_connect_failed", org_id=str(org_id), error=exc.code)
        outcome = "rotation" if exc.code == "token_rotation_on" else "failed"
    except httpx.HTTPError as exc:
        logger.warning("slack_status_connect_failed", org_id=str(org_id), error=str(exc))
        outcome = "failed"
    else:
        await db.commit()
        await hand_back(connected.stale_tokens)
        spawn(refresh_member(org_id, user_id))
        return SlackStatusFinished(outcome="moved" if connected.moved else "connected")
    # Nothing of a refused connect is kept (a self-link included).
    await db.rollback()
    return SlackStatusFinished(outcome=outcome)


@router.delete("/slack-status/me", status_code=204)
async def disconnect_my_slack_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Stop setting the caller's status: take ours off, forget the token, hand it back."""
    links = SlackStatusLinkRepository(db, org_id=current_user.org_id)
    link = await links.for_user(current_user.id)
    if link is None:
        return
    token = await forget(db, link, keep_to_retry=False)
    await db.commit()
    if token:
        await hand_back([token])
