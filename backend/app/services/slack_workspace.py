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

"""Proving an org's Slack bot token belongs to the workspace it claims.

The team id maps incoming Slack events and buttons to an org, so it is
only ever taken from Slack itself (auth.test on the org's own bot token),
never from what someone typed: otherwise any org could claim another
org's workspace and lock it out.
"""

from app.core.encryption import decrypt_secret
from app.services.slack_client import auth_test


async def bot_token_team(encrypted_bot_token: str | None) -> str | None:
    """The workspace Slack says ``encrypted_bot_token`` belongs to, or None."""
    if not encrypted_bot_token:
        return None
    info = await auth_test(decrypt_secret(encrypted_bot_token))
    team = (info or {}).get("team_id")
    return str(team) if team else None
