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

"""Slack interactivity: button clicks and modal submissions.

Configure the Slack app's Interactivity "Request URL" to
``https://<host>/api/v1/slack/interactions``. There is no login: every
request must carry a valid Slack signature for the workspace's org.
"""

import json
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.services.leave.slack_actions import handle_interaction
from app.services.slack_verify import verified_org

router = APIRouter(tags=["slack"])


@router.post("/interactions", response_model=None)
async def slack_interactions(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Verify and handle one Slack interaction."""
    raw = await request.body()
    try:
        payload: dict[str, Any] = json.loads(parse_qs(raw.decode("utf-8"))["payload"][0])
    except (KeyError, IndexError, ValueError):
        return Response(status_code=400)
    if not isinstance(payload, dict):
        return Response(status_code=400)
    team = payload.get("team") or {}
    team_id = str(team.get("id") or (payload.get("user") or {}).get("team_id") or "")
    org = await verified_org(
        db,
        team_id,
        request.headers.get("X-Slack-Request-Timestamp", ""),
        raw,
        request.headers.get("X-Slack-Signature", ""),
    )
    if org is None:
        return Response(status_code=401)
    body = await handle_interaction(db, org, payload)
    return JSONResponse(body) if body else Response(status_code=200)
