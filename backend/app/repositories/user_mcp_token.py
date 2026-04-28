# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""UserMCPToken data access repository."""

from sqlalchemy import select
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
