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

"""UserMCPToken data access repository."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user_mcp_token import UserMCPToken
from app.repositories.base import BaseRepository


class UserMCPTokenRepository(BaseRepository[UserMCPToken]):
    """Repository for per-user MCP tokens.

    Token lookups during MCP auth are global (no org scope) — the token
    itself binds to an org once verified.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(UserMCPToken, db)

    async def list_by_prefix_with_relations(self, prefix: str) -> list[UserMCPToken]:
        """All tokens whose ``token_prefix`` matches, with user + org eager-loaded.

        Args:
            prefix: The non-secret token prefix used for indexed lookup.

        Returns:
            List of candidate tokens — the caller must still bcrypt-verify
            ``token_hash`` against the plaintext.
        """
        result = await self._db.execute(
            select(UserMCPToken)
            .where(UserMCPToken.token_prefix == prefix)
            .options(
                selectinload(UserMCPToken.user),
                selectinload(UserMCPToken.organization),
            )
        )
        return list(result.scalars().all())

    async def get_by_user_org_name(
        self, user_id: uuid.UUID, org_id: uuid.UUID, name: str
    ) -> UserMCPToken | None:
        """Fetch one token by its (user, org, name) tuple."""
        result = await self._db.execute(
            select(UserMCPToken).where(
                UserMCPToken.user_id == user_id,
                UserMCPToken.org_id == org_id,
                UserMCPToken.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID, org_id: uuid.UUID) -> list[UserMCPToken]:
        """All tokens belonging to the caller, newest first.

        Used by ``GET /v1/me/mcp-tokens`` for the connect panel.
        """
        result = await self._db.execute(
            select(UserMCPToken)
            .where(UserMCPToken.user_id == user_id, UserMCPToken.org_id == org_id)
            .order_by(UserMCPToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_org(self, org_id: uuid.UUID) -> list[UserMCPToken]:
        """All tokens issued within an org, newest first.

        Used by the admin org-wide visibility endpoint so an owner can
        spot leaked/forgotten tokens belonging to any team member.
        """
        result = await self._db.execute(
            select(UserMCPToken)
            .where(UserMCPToken.org_id == org_id)
            .options(selectinload(UserMCPToken.user))
            .order_by(UserMCPToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_for_user(
        self, token_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> int:
        """Revoke one of the caller's own tokens. Returns rowcount."""
        result = await self._db.execute(
            delete(UserMCPToken).where(
                UserMCPToken.id == token_id,
                UserMCPToken.user_id == user_id,
                UserMCPToken.org_id == org_id,
            )
        )
        # ``rowcount`` is exposed on CursorResult (returned by DML statements)
        # but isn't part of the generic Result[Any] protocol that the
        # session.execute() stub advertises. ``getattr`` keeps mypy strict-clean
        # without a per-line ``type: ignore``.
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_for_org(self, token_id: uuid.UUID, org_id: uuid.UUID) -> int:
        """Admin revoke — drops any token within the admin's org. Returns rowcount."""
        result = await self._db.execute(
            delete(UserMCPToken).where(
                UserMCPToken.id == token_id,
                UserMCPToken.org_id == org_id,
            )
        )
        # ``rowcount`` is exposed on CursorResult (returned by DML statements)
        # but isn't part of the generic Result[Any] protocol that the
        # session.execute() stub advertises. ``getattr`` keeps mypy strict-clean
        # without a per-line ``type: ignore``.
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke EVERY token belonging to a user, across all orgs.

        Called from the member-deactivation / merge paths because
        ``users.is_active = False`` is a soft delete that does NOT fire
        the FK CASCADE on ``user_mcp_tokens.user_id``. Without this,
        a deactivated member's bodhi_token would keep authenticating
        to /mcp/* until manually revoked.
        """
        result = await self._db.execute(
            delete(UserMCPToken).where(UserMCPToken.user_id == user_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def touch_last_used(self, token_id: uuid.UUID) -> None:
        """Update ``last_used_at`` to now. Fire-and-forget from the MCP auth path."""
        await self._db.execute(
            update(UserMCPToken)
            .where(UserMCPToken.id == token_id)
            .values(last_used_at=datetime.now(UTC))
        )
