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

"""Admin org-wide MCP token visibility and revocation.

Lets an org owner / admin see every per-user MCP token issued inside
their tenancy and revoke any of them — required for incident response
(a leaked token belonging to a team member) and offboarding (a former
employee whose long-lived tokens are still active).

Self-service per-user management (mint your own / list your own /
revoke your own) lives in ``api/v1/me.py``. This module ONLY exposes
the admin org-wide endpoints, gated by ``org:edit_settings``.
"""

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.user_mcp_token import UserMCPTokenRepository

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings"])


class OrgMCPTokenRead(BaseModel):
    """Listing entry for the admin org-wide token list."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    user_name: str | None
    name: str
    token_prefix: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


@router.get(
    "/mcp-tokens",
    response_model=list[OrgMCPTokenRead],
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def list_org_mcp_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrgMCPTokenRead]:
    """List every MCP token issued within the caller's org. No plaintext."""
    rows = await UserMCPTokenRepository(db).list_for_org(current_user.org_id)
    return [
        OrgMCPTokenRead(
            id=r.id,
            user_id=r.user_id,
            user_email=r.user.email if r.user else "",
            user_name=r.user.name if r.user else None,
            name=r.name,
            token_prefix=r.token_prefix,
            expires_at=r.expires_at,
            last_used_at=r.last_used_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.delete(
    "/mcp-tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def revoke_org_mcp_token(
    token_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke any token belonging to a user in the caller's org."""
    deleted = await UserMCPTokenRepository(db).delete_for_org(token_id, current_user.org_id)
    if deleted == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    logger.info(
        "org_admin_mcp_token_revoked",
        org_id=str(current_user.org_id),
        revoked_by=current_user.email,
        token_id=str(token_id),
    )
