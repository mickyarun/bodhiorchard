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

It's a browser redirect with no login, so it doesn't finish anything: it
hands ``code`` and ``state`` to the Leave page, which finishes while signed
in (``POST /leave/slack-status/me/finish``). That way a connect link opened
by anyone but the member who started it goes nowhere, even if they approve.
"""

from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.config import settings

router = APIRouter(tags=["slack"])


@router.get("/status/callback", response_class=RedirectResponse)
async def slack_status_callback(
    state: str = "", code: str = "", error: str = ""
) -> RedirectResponse:
    """Back to the Leave page, with what Slack sent for it to finish."""
    if error:
        # They pressed Cancel on Slack's page.
        query = {"slackStatus": "cancelled"}
    elif not code or not state:
        query = {"slackStatus": "failed"}
    else:
        query = {"slackCode": code, "slackState": state}
    return RedirectResponse(f"{settings.frontend_url}/leave?{urlencode(query)}", 303)
