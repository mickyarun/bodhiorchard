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

"""Fire-and-forget audit-log writer for MCP tool calls.

Audit writes use their own database session because the request session
may already be torn down by the time the response is being serialized.
Failures are swallowed (logged) — a transient Postgres hiccup must not
break the user-facing MCP response.
"""

import asyncio
import uuid

import structlog
from fastapi import Request

from app.database import AsyncSessionLocal
from app.mcp.auth import MCPAuthResult
from app.repositories.mcp_audit_log import MCPAuditLogRepository

logger = structlog.get_logger(__name__)

# Holds in-flight audit tasks so they aren't garbage-collected mid-flight;
# each task removes itself on completion.
_audit_tasks: set[asyncio.Task[None]] = set()

# Cap on concurrent in-flight audit writes. Hit it during a burst and we
# drop the audit (logged at warning) rather than spawn unbounded tasks
# or block the auth path. 1000 is well above realistic per-instance load.
_MAX_INFLIGHT = 1000


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP. Trusts X-Forwarded-For only if Caddy set it."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Caddy appends the originating IP first; trust only the leftmost.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _write_audit_row(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    token_id: uuid.UUID | None,
    tool_name: str,
    transport: str,
    ip: str | None,
    user_agent: str | None,
    status_code: int,
) -> None:
    """Internal: insert one audit row using a fresh session."""
    try:
        async with AsyncSessionLocal() as session:
            await MCPAuditLogRepository(session).record(
                org_id=org_id,
                user_id=user_id,
                token_id=token_id,
                tool_name=tool_name,
                transport=transport,
                ip=ip,
                user_agent=user_agent,
                status_code=status_code,
            )
            await session.commit()
    except Exception:
        logger.exception(
            "mcp_audit_write_failed",
            tool=tool_name,
            org_id=str(org_id),
            status_code=status_code,
        )


def emit_audit(
    *,
    request: Request,
    auth: MCPAuthResult | None,
    org_id: uuid.UUID,
    token_id: uuid.UUID | None,
    tool_name: str,
    transport: str,
    status_code: int,
) -> None:
    """Schedule a fire-and-forget audit write.

    Safe to call from any handler — never raises, never blocks. ``auth``
    is optional so a 401 (before auth resolves) can still record an
    attempt against the resolved org if one is available later via the
    bearer prefix; pass ``None`` when nothing is known.
    """
    if len(_audit_tasks) >= _MAX_INFLIGHT:
        logger.warning(
            "mcp_audit_inflight_cap_hit",
            tool=tool_name,
            dropped=True,
            inflight=len(_audit_tasks),
        )
        return
    task = asyncio.create_task(
        _write_audit_row(
            org_id=org_id,
            user_id=auth.user.id if auth and auth.user else None,
            token_id=token_id,
            tool_name=tool_name,
            transport=transport,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            status_code=status_code,
        )
    )
    _audit_tasks.add(task)
    task.add_done_callback(_audit_tasks.discard)
