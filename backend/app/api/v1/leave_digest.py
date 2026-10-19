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

"""Settings for the daily who's-out Slack post, and a test post (HR)."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._leave_admin import CONFIGURE
from app.core.deps import get_db, require_permissions
from app.models.user import User
from app.schemas.leave_digest import DigestTestResult, LeaveDigestSettings
from app.services.leave.digest_build import build_digest
from app.services.leave.digest_settings import (
    digest_zone,
    load_digest_settings,
    save_digest_settings,
)
from app.services.slack_dm import bot_token
from app.services.slack_interactive import post_message

router = APIRouter(tags=["leave-admin"])

SAMPLE = "Test from Bodhiorchard: the daily who's-out post will appear in this channel."


@router.get("/digest-settings", response_model=LeaveDigestSettings)
async def get_digest_settings(
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> LeaveDigestSettings:
    """The org's daily post settings."""
    return await load_digest_settings(db, current_user.org_id)


@router.put("/digest-settings", response_model=LeaveDigestSettings)
async def put_digest_settings(
    body: LeaveDigestSettings,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> LeaveDigestSettings:
    """Save the daily post settings."""
    await save_digest_settings(db, current_user.org_id, body)
    return body


@router.post("/digest/test", response_model=DigestTestResult)
async def send_test_post(
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> DigestTestResult:
    """Post today's message now (or a sample if nobody is out) to the saved channel."""
    settings = await load_digest_settings(db, current_user.org_id)
    if not settings.channel_id:
        return DigestTestResult(ok=False, error="no_channel", text="")
    token = await bot_token(db, current_user.org_id)
    if not token:
        return DigestTestResult(ok=False, error="slack_not_connected", text="")
    today = datetime.now(await digest_zone(db, current_user.org_id, settings)).date()
    text = await build_digest(db, current_user.org_id, today) or SAMPLE
    _channel, _ts, error = await post_message(token, settings.channel_id, text)
    return DigestTestResult(ok=not error, error=error or None, text=text)
