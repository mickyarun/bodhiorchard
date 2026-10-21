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
"""Access tokens for a service account acting as a Workspace user.

A Workspace admin grants the service account domain-wide delegation for
the scopes we ask for; we then sign a JWT naming the user (``sub``) and
trade it for an access token. Tokens are cached per (private key, user,
scope) until a minute before they expire.

The key's own ``token_uri`` is ignored: an uploaded file must never decide
where the server sends requests.
"""

import hashlib
import json
import time
from dataclasses import dataclass

import httpx
import jwt

TOKEN_URI = "https://oauth2.googleapis.com/token"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
HTTP_TIMEOUT_SECONDS = 15
_ASSERTION_TTL_SECONDS = 3600
_MAX_TOKEN_SECONDS = 3600
_REFRESH_MARGIN_SECONDS = 60

_cache: dict[tuple[str, str, str], tuple[str, float]] = {}


class GoogleAuthError(Exception):
    """The key is unusable, or Google refused to act as this user.

    ``code`` is Google's error (``unauthorized_client`` = delegation not
    granted for the scope; ``invalid_grant`` = no such user on the domain).
    """

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class ServiceAccountKey:
    """The parts of a downloaded JSON key we use."""

    client_email: str
    private_key: str

    @property
    def fingerprint(self) -> str:
        """Identifies the key itself; the email alone is public and forgeable."""
        return hashlib.sha256(self.private_key.encode()).hexdigest()


def parse_key(raw: str) -> ServiceAccountKey:
    """Read a service account JSON key; :class:`GoogleAuthError` if it isn't one."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GoogleAuthError("invalid_key", "not JSON") from exc
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise GoogleAuthError("invalid_key", "not a service account key")
    email, private_key = data.get("client_email"), data.get("private_key")
    if not isinstance(email, str) or not isinstance(private_key, str):
        raise GoogleAuthError("invalid_key", "missing client_email or private_key")
    return ServiceAccountKey(email, private_key)


async def access_token(key: ServiceAccountKey, user_email: str, scope: str) -> str:
    """A token to call Google as ``user_email``; cached until shortly before expiry."""
    cache_key = (key.fingerprint, user_email.lower(), scope)
    cached = _cache.get(cache_key)
    if cached and cached[1] > time.time():
        return cached[0]
    now = int(time.time())
    claims = {
        "iss": key.client_email,
        "sub": user_email,
        "scope": scope,
        "aud": TOKEN_URI,
        "iat": now,
        "exp": now + _ASSERTION_TTL_SECONDS,
    }
    try:
        assertion = jwt.encode(claims, key.private_key, algorithm="RS256")
    except (ValueError, TypeError) as exc:
        raise GoogleAuthError("invalid_key", "private key can't sign") from exc
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            TOKEN_URI, data={"grant_type": GRANT_TYPE, "assertion": assertion}
        )
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or not isinstance(body, dict) or "access_token" not in body:
        body = body if isinstance(body, dict) else {}
        raise GoogleAuthError(
            str(body.get("error", response.status_code)), str(body.get("error_description", ""))
        )
    lifetime = min(int(body.get("expires_in", _MAX_TOKEN_SECONDS)), _MAX_TOKEN_SECONDS)
    expires = now + lifetime - _REFRESH_MARGIN_SECONDS
    _cache[cache_key] = (body["access_token"], expires)
    return str(body["access_token"])
