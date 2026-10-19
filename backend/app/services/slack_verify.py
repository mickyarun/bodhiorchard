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

"""Verifying that a request really came from Slack (HMAC-SHA256, v0 scheme).

Shared by the Events API webhook and the interactivity endpoint (button
clicks, modal submissions). The org is found by Slack team id and its
own signing secret checks the signature; requests older than five
minutes are refused so a captured one can't be replayed later.
"""

import hashlib
import hmac
import time

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.models.organization import Organization
from app.repositories.organization import OrganizationRepository

logger = structlog.get_logger(__name__)

MAX_AGE_SECONDS = 300


def verify_slack_signature(
    signing_secret: str, timestamp: str, body: bytes, signature: str
) -> tuple[bool, str]:
    """Check a Slack signature; returns ``(is_valid, reason)`` (reason empty if valid).

    The reason never includes any part of the secret.
    """
    try:
        drift = abs(time.time() - int(timestamp))
    except ValueError:
        return False, "bad_timestamp"
    if drift > MAX_AGE_SECONDS:
        return False, f"timestamp_drift={int(drift)}s"
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(signing_secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256)
    computed = "v0=" + digest.hexdigest()
    if hmac.compare_digest(computed.encode(), signature.encode("utf-8", "replace")):
        return True, ""
    return False, f"hmac_mismatch body_len={len(body)}"


async def verified_org(
    db: AsyncSession, team_id: str, timestamp: str, body: bytes, signature: str
) -> Organization | None:
    """The org for ``team_id`` if the request is signed with its secret, else None."""
    if not team_id or not timestamp or not signature:
        logger.warning("slack_request_missing_fields", team_id=team_id)
        return None
    org = await OrganizationRepository(db).get_by_slack_team_id(team_id)
    if org is None or not org.slack_signing_secret:
        logger.warning("slack_org_not_found_or_no_secret", team_id=team_id)
        return None
    secret = decrypt_secret(org.slack_signing_secret)
    if not secret:
        logger.error("slack_signing_secret_decrypt_failed", team_id=team_id)
        return None
    valid, reason = verify_slack_signature(secret, timestamp, body, signature)
    if not valid:
        logger.warning("slack_signature_invalid", team_id=team_id, reason=reason)
        return None
    return org
