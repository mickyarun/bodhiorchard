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

"""Where Slack sends a member back after they approve status updates.

No login (it's a browser redirect from Slack): who it's for comes from the
signed ``state``. Always ends on the member's Leave page with the outcome.
"""

import httpx
import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_db
from app.services.background import spawn
from app.services.leave.slack_status.apply import hand_back, refresh_member
from app.services.leave.slack_status.oauth import (
    InvalidStateError,
    WrongSlackAccountError,
    complete,
    read_state,
)
from app.services.leave.slack_status.settings import load_client
from app.services.slack_user_api import SlackUserApiError

router = APIRouter(tags=["slack"])
logger = structlog.get_logger(__name__)


def _back(outcome: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url}/leave?slackStatus={outcome}", 303)


@router.get("/status/callback", response_class=RedirectResponse)
async def slack_status_callback(
    state: str = "",
    code: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Finish the approval: keep the token, set today's status, go back to the app."""
    if error:
        # They pressed Cancel on Slack's page.
        return _back("cancelled")
    try:
        org_id, user_id = read_state(state)
    except InvalidStateError:
        return _back("expired")
    client = await load_client(db, org_id)
    if not client.ready or not code:
        return _back("failed")
    try:
        connected = await complete(db, client, org_id, user_id, code)
    except WrongSlackAccountError:
        return _back("wrong_account")
    except SlackUserApiError as exc:
        logger.warning("slack_status_connect_failed", org_id=str(org_id), error=exc.code)
        return _back("rotation" if exc.code == "token_rotation_on" else "failed")
    except httpx.HTTPError as exc:
        logger.warning("slack_status_connect_failed", org_id=str(org_id), error=str(exc))
        return _back("failed")
    await db.commit()
    await hand_back(connected.stale_tokens)
    spawn(refresh_member(org_id, user_id))
    return _back("moved" if connected.moved else "connected")
