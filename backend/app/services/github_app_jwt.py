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

"""Shared GitHub App JWT helpers and HTTP constants.

Lives in its own module so :mod:`app.services.github_app_auth` (token
exchange) and :mod:`app.services.github_app_slug` (slug retrofit) can
both depend on the same primitives without one importing the other.
"""

import time

import jwt

GITHUB_BASE_URL = "https://api.github.com"
GITHUB_APP_ENDPOINT = f"{GITHUB_BASE_URL}/app"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_ACCEPT = "application/vnd.github+json"
HTTP_TIMEOUT_SECONDS = 15
# The public install URL — needs the App's slug, populated lazily by the
# slug-retrofit path. Lives here (not in the route module) so service-layer
# code can import it without creating a cycle through ``app.api.v1.settings``.
GITHUB_APP_INSTALL_URL_TEMPLATE = "https://github.com/apps/{slug}/installations/new"

# JWT issued to the App is valid for 10 minutes; allow 60s clock drift
# either side per GitHub's docs.
_JWT_TTL_SECONDS = 10 * 60
_JWT_DRIFT_SECONDS = 60


def generate_app_jwt(app_id: int, private_key_pem: str) -> str:
    """Create a JWT signed with the App's private key (10 min TTL)."""
    now = int(time.time())
    payload = {
        "iat": now - _JWT_DRIFT_SECONDS,
        "exp": now + _JWT_TTL_SECONDS,
        "iss": str(app_id),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def app_jwt_headers(app_jwt: str) -> dict[str, str]:
    """Build the standard headers for an App-JWT-authenticated GitHub call."""
    return {
        "Accept": GITHUB_ACCEPT,
        "Authorization": f"Bearer {app_jwt}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
