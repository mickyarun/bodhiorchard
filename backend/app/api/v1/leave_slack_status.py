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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.slack_status_link import SlackStatusLinkRepository
from app.schemas.leave_slack_status import (
    SlackStatusConnect,
    SlackStatusMine,
    SlackStatusSettings,
    SlackStatusUpdate,
)
from app.services.background import spawn
from app.services.leave.permissions import CONFIGURE
from app.services.leave.slack_status.apply import forget, hand_back
from app.services.leave.slack_status.oauth import authorize_url
from app.services.leave.slack_status.scheduler import clear_all
from app.services.leave.slack_status.settings import load_client, load_settings, save_settings

router = APIRouter(tags=["leave"])


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
