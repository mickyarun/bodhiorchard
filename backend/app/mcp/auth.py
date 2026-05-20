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

"""MCP token verification for Bodhiorchard tool calls from Claude Code."""

import asyncio
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import hash_password, verify_password
from app.database import AsyncSessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.user_mcp_token import UserMCPTokenRepository

logger = structlog.get_logger(__name__)

# Internal tokens: short-lived tokens for scan-initiated Claude CLI runs.
# Maps token → org_id. Populated by create_internal_mcp_token(),
# consumed by verify_mcp_token(). Tokens persist until server restart;
# eager revocation caused race conditions with the shared token file.
_internal_tokens: dict[str, uuid.UUID] = {}
_MAX_INTERNAL_TOKENS = 100

# Pre-computed bcrypt hash of a fixed throwaway value. Used to equalize
# response time on the no-prefix-match path so attackers can't enumerate
# valid token prefixes by timing the bcrypt round-trip. Computed once at
# import-time so verify_mcp_token() itself never blocks on the hash op.
_TIMING_EQUALIZER_HASH = hash_password("bodhiorchard-timing-equalizer-not-a-real-token")

# Track in-flight last-used-touch tasks so they aren't garbage-collected
# mid-flight; each task removes itself on completion.
_last_used_tasks: set[asyncio.Task[None]] = set()


def compute_token_prefix(plaintext_token: str) -> str:
    """Compute a non-secret prefix for indexed token lookup.

    Uses SHA-256 of the plaintext, truncated to 16 hex chars.
    This is NOT a secret — it's stored in plaintext for fast filtering
    before the expensive bcrypt verification.

    Args:
        plaintext_token: The raw token string.

    Returns:
        16-character hex prefix.
    """
    return hashlib.sha256(plaintext_token.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class MCPAuthResult:
    """Result of MCP token verification.

    Always contains an org. Contains a user when the token is
    a per-user token (UserMCPToken), None for org-level or internal tokens.
    ``token_id`` is the UserMCPToken row id when the call was authenticated
    by a per-user token — used by the audit log so an admin can trace any
    recorded action back to a specific revocable credential.
    """

    org: Organization
    user: User | None = None
    token_id: uuid.UUID | None = None


def create_internal_mcp_token(org_id: uuid.UUID) -> str:
    """Create a temporary MCP token for internal use (e.g. scan pipeline).

    The token is stored in-memory and valid until server restart.
    If the token pool exceeds ``_MAX_INTERNAL_TOKENS``, the oldest
    entry is evicted to bound memory usage.

    Args:
        org_id: The organization UUID to associate with the token.

    Returns:
        The plaintext token string.
    """
    token = secrets.token_urlsafe(32)
    # Evict oldest token if at capacity
    if len(_internal_tokens) >= _MAX_INTERNAL_TOKENS:
        oldest_key = next(iter(_internal_tokens))
        _internal_tokens.pop(oldest_key)
        logger.debug("internal_token_evicted", evicted_token=oldest_key[:8])
    _internal_tokens[token] = org_id
    return token


def _is_expired(expires_at: datetime | None) -> bool:
    """True if a token has an expiry that's already in the past."""
    if expires_at is None:
        return False
    return expires_at <= datetime.now(UTC)


async def _touch_last_used(token_id: uuid.UUID, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Background task: bump ``last_used_at`` on a successful auth.

    Uses its own session — the request's session may be torn down before
    this background write completes. Failures are swallowed (logged WITH
    full context so a consistent FK / column mismatch surfaces in alerts)
    so a transient DB hiccup never breaks the user-facing auth path.
    """
    try:
        async with AsyncSessionLocal() as session:
            await UserMCPTokenRepository(session).touch_last_used(token_id)
            await session.commit()
    except Exception:
        logger.exception(
            "mcp_token_last_used_touch_failed",
            token_id=str(token_id),
            org_id=str(org_id),
            user_id=str(user_id),
        )


def _schedule_last_used(token_id: uuid.UUID, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Fire-and-forget last-used touch — never blocks the auth path."""
    task = asyncio.create_task(_touch_last_used(token_id, org_id, user_id))
    _last_used_tasks.add(task)
    task.add_done_callback(_last_used_tasks.discard)


async def verify_mcp_token(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(),
) -> MCPAuthResult:
    """Verify the bearer token from an MCP request.

    Resolution order:
    1. Internal tokens (in-memory, scan pipeline) → org only.
       Expiry/scope checks are intentionally skipped — internal tokens
       are server-minted, never leave the host, and represent trusted
       full-access scope for the scan pipeline.
    2. Per-user tokens (UserMCPToken table) → org + user.
       Rejected if ``expires_at`` has passed; ``last_used_at`` is
       updated in the background on success.
    3. Org-level tokens (Organization.mcp_token_hash) → org only.

    Args:
        db: The async database session.
        authorization: The Authorization header value (Bearer <token>).

    Returns:
        MCPAuthResult with the authenticated org and optional user.

    Raises:
        HTTPException: If token is missing, invalid, or no match found.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = authorization[7:]

    logger.debug(
        "mcp_auth_attempt",
        token_prefix=token[:8] if len(token) >= 8 else token,
        internal_token_count=len(_internal_tokens),
    )

    org_repo = OrganizationRepository(db)

    # 1. Check internal tokens first (fast, in-memory). No expiry check —
    # internal tokens are server-minted for the scan pipeline.
    internal_org_id = _internal_tokens.get(token)
    if internal_org_id is not None:
        org = await org_repo.get_by_id(internal_org_id)
        if org:
            logger.debug("mcp_auth_internal", org_id=str(org.id))
            return MCPAuthResult(org=org)

    # 2. Check per-user tokens — filter by prefix (indexed), then bcrypt.
    # Expired rows still go through bcrypt to keep the timing consistent
    # whether the token "doesn't exist" vs "exists but expired".
    prefix = compute_token_prefix(token)
    candidates = await UserMCPTokenRepository(db).list_by_prefix_with_relations(prefix)
    for ut in candidates:
        if not verify_password(token, ut.token_hash):
            continue
        if _is_expired(ut.expires_at):
            logger.info(
                "mcp_auth_user_token_expired",
                token_id=str(ut.id),
                org_id=str(ut.org_id),
                user_id=str(ut.user_id),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        # Defence-in-depth: ``users.is_active = False`` is a soft delete
        # used by member-deactivation and member-merge. The token-revoke
        # at deactivation time handles the happy path, but this check
        # rejects any token that survives that step (race, missed call
        # site, stale row) before it can read org data. Distinct log line
        # so an unexpected revival surfaces in alerts.
        if ut.user is not None and not ut.user.is_active:
            logger.info(
                "mcp_auth_user_token_inactive_user",
                token_id=str(ut.id),
                org_id=str(ut.org_id),
                user_id=str(ut.user_id),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated",
            )
        _schedule_last_used(ut.id, ut.org_id, ut.user_id)
        logger.debug(
            "mcp_auth_user_token",
            org_id=str(ut.org_id),
            user_id=str(ut.user_id),
            token_id=str(ut.id),
        )
        return MCPAuthResult(org=ut.organization, user=ut.user, token_id=ut.id)

    # 3. Fall back to org-level token hashes.
    orgs = await org_repo.get_all_with_mcp_tokens()
    for org in orgs:
        if org.mcp_token_hash and verify_password(token, org.mcp_token_hash):
            logger.debug(
                "mcp_auth_success",
                org_id=str(org.id),
                slug=org.slug,
            )
            return MCPAuthResult(org=org)

    # Equalize timing: if no prefix matched AND no org token matched, run a
    # dummy bcrypt so the response time matches the "prefix matched but
    # bcrypt failed" path. Closes a token-prefix-enumeration side channel.
    # Narrow except so a broken/misconfigured bcrypt backend surfaces as a
    # WARNING rather than being hidden behind the uniform 401 below.
    if not candidates:
        try:
            verify_password(token, _TIMING_EQUALIZER_HASH)
        except ValueError:
            logger.warning("mcp_timing_equalizer_failed")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired MCP token",
    )
