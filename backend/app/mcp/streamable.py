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

"""Remote MCP endpoint for external LLM clients (Claude Desktop / Cursor / Continue).

Implements the read-only subset of the MCP ``2025-03-26/streamable-http``
transport spec — enough for desktop AI clients to ``initialize``,
``tools/list`` and ``tools/call`` against the four tools the user explicitly
exposes to BYO-AI workflows.

**Why a separate endpoint?** The existing ``POST /mcp/tools/{name}`` path
exposes every tool (incl. ``write_bud``, ``code_*``, scan helpers) to the
in-process stdio bridge and the scan pipeline. Those are trusted callers.
The remote endpoint must NOT widen that surface — so the allowlist is
enforced at this transport layer, NOT per-token scopes. Adding a new tool
to ``TOOL_HANDLERS`` therefore cannot accidentally make it remote-callable;
that requires explicit addition to ``REMOTE_TOOLS`` here.

**SSE handling.** Desktop clients open a GET SSE stream alongside POSTs.
We keep it alive with a heartbeat and re-verify the token on every beat;
a revoked or expired token drops the stream so the client must re-auth.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.database import AsyncSessionLocal
from app.mcp.audit import emit_audit
from app.mcp.auth import MCPAuthResult, verify_mcp_token
from app.mcp.handlers_prompts import CANONICAL_TASK_TYPES
from app.mcp.rate_limit import enforce_rate_limit
from app.repositories.user_mcp_token import UserMCPTokenRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp-remote"])

# Hard-coded read-only allowlist. Anything not in this set returns
# JSON-RPC -32601 "method not found" from the remote endpoint, regardless
# of what is registered in ``TOOL_HANDLERS``. This is intentional — see
# the module docstring.
REMOTE_TOOLS: frozenset[str] = frozenset(
    {
        "get_bud_context",
        "get_features",
        "list_design_systems",
        "get_design_system",
        "get_prompt",
        # BYO-AI write surface. Gated additionally at the handler layer
        # (assignee-only, content-only-within-current-phase) — see
        # ``handlers_bud_writes.py``.
        "create_bud",
        "update_bud",
        "get_bud_by_id",
    }
)

# Tool-call descriptors exposed via ``tools/list``. Kept in-module rather
# than re-imported from ``server.MCP_TOOLS`` so the remote schema can
# present BYO-AI-friendly wording without coupling to the internal-tool
# definitions.
_REMOTE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_bud_context",
        "description": (
            "List in-progress BUDs (not closed/discarded) in your org "
            "for context when drafting a new one. Optional ``query`` "
            "does substring keyword search on title + requirements_md "
            "(same tokenisation as get_features). Pass "
            "include_terminal=true to also see closed/discarded history."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "query": {"type": "string"},
                "include_terminal": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "get_features",
        "description": (
            "Hybrid search over your org's active features. Title-substring match "
            "first (mirrors the frontend /features page), with semantic-embedding "
            "fallback when the literal phrase isn't in any title. ALWAYS pass a "
            "non-empty ``query``. Paginate via ``offset`` + ``next_offset`` until "
            "``has_more`` is false. Each result has an ``id`` you can place into a "
            'BUD\'s trailing {"linked_feature_ids": [...]} fence.'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_design_systems",
        "description": "List design system metadata available to your org (one per repo).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_design_system",
        "description": (
            "Return the full design system HTML/CSS/tokens for a specific repo, or "
            "the org default if no repo_id is supplied."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"repo_id": {"type": "string"}},
        },
    },
    {
        "name": "create_bud",
        "description": (
            "Create a new BUD in your org. You become both creator and "
            "assignee so subsequent update_bud calls from this token can "
            "find it. Empty title or requirements_md is rejected. Pass "
            "linked_feature_ids (UUIDs from get_features) to wire feature "
            "links in the same call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "requirements_md": {"type": "string"},
                "linked_feature_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["title", "requirements_md"],
        },
    },
    {
        "name": "update_bud",
        "description": (
            "Update content for the BUD's current creative phase. "
            "Editable phases: BUD (requirements_md), DESIGN (BUD-level "
            "wireframe HTML), TECH_ARCH (tech_spec_md). Other phases "
            "(testing, code_review, …) are NOT remotely writable. You "
            "must be the BUD's assignee; the server picks the field "
            "from the phase — you cannot address a different one. "
            "Optional linked_feature_ids is idempotent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bud_id": {"type": "string"},
                "content": {"type": "string"},
                "linked_feature_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["bud_id", "content"],
        },
    },
    {
        "name": "get_bud_by_id",
        "description": (
            "Fetch a single BUD by UUID with the full body of every "
            "section (per-field truncation applied)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"bud_id": {"type": "string"}},
            "required": ["bud_id"],
        },
    },
    {
        "name": "get_prompt",
        "description": (
            "Return the exact prompt our agent would use for a given BUD "
            "stage. Feed it to your local AI to produce content that "
            "matches the shape the BUD section editors expect."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    # Advertise the canonical role-based names — shared
                    # with server.py MCP_TOOLS so the remote-advertised
                    # enum can't drift. Internal phase-name aliases
                    # (``bud``, ``tech_arch``) still work but aren't
                    # surfaced to discourage drift between the two
                    # vocabularies.
                    "enum": list(CANONICAL_TASK_TYPES),
                },
            },
            "required": ["task_type"],
        },
    },
]

# JSON-RPC error codes (subset we use).
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INTERNAL_ERROR = -32603


def _rpc_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def _dispatch(
    method: str,
    params: dict[str, Any],
    db: AsyncSession,
    auth: MCPAuthResult,
) -> Any:
    """Dispatch a single MCP method to the underlying handler."""
    if method == "initialize":
        return {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "bodhiorchard", "version": "0.1.0"},
        }

    if method == "tools/list":
        return {"tools": _REMOTE_TOOL_SCHEMAS}

    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments") or {}
        if not isinstance(tool_name, str) or tool_name not in REMOTE_TOOLS:
            raise _RPCError(_METHOD_NOT_FOUND, f"Tool not available remotely: {tool_name!r}")
        # Import locally to avoid a circular import with server.py's
        # TOOL_HANDLERS dict (server.py imports this module to mount it).
        from app.mcp.server import AUTH_TOOL_HANDLERS, TOOL_HANDLERS

        # Auth-aware handlers receive the full MCPAuthResult so they can
        # enforce per-user guards (e.g. update_bud's assignee check).
        auth_handler = AUTH_TOOL_HANDLERS.get(tool_name)
        handler = TOOL_HANDLERS.get(tool_name)
        if auth_handler is not None:
            result = await auth_handler(db, auth, tool_args)
        elif handler is not None:
            result = await handler(db, auth.org, tool_args)
        else:
            raise _RPCError(_INTERNAL_ERROR, f"Handler missing for {tool_name!r}")
        # Wrap raw handler output in the MCP tools/call response envelope.
        # Handlers signal a soft failure (bad params, missing seed data) by
        # returning a dict with an ``error`` key instead of raising — propagate
        # that to ``isError: true`` so desktop clients route it through their
        # error UI rather than feeding the error text into the LLM as a prompt.
        is_error = isinstance(result, dict) and "error" in result
        return {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "isError": is_error,
        }

    raise _RPCError(_METHOD_NOT_FOUND, f"Unknown method: {method!r}")


class _RPCError(Exception):
    """Signals a JSON-RPC-shaped error from inside dispatch."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@router.post("/sse")
async def remote_mcp_post(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: MCPAuthResult = Depends(verify_mcp_token),
) -> JSONResponse:
    """JSON-RPC over POST — primary message channel for desktop MCP clients."""
    try:
        body = await request.json()
    except Exception:
        # Auth already passed via the Depends, so org/token are known —
        # record the parse failure so probing leaves a forensic trail.
        emit_audit(
            request=request,
            auth=auth,
            org_id=auth.org.id,
            token_id=auth.token_id,
            tool_name="<parse_error>",
            transport="sse",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        return JSONResponse(_rpc_error(None, _PARSE_ERROR, "Invalid JSON"), status_code=400)

    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return JSONResponse(
            _rpc_error(
                body.get("id") if isinstance(body, dict) else None,
                _INVALID_REQUEST,
                "Expected JSON-RPC 2.0 envelope",
            ),
            status_code=400,
        )

    req_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params") or {}
    if not isinstance(method, str) or not isinstance(params, dict):
        return JSONResponse(
            _rpc_error(req_id, _INVALID_REQUEST, "method/params malformed"),
            status_code=400,
        )

    # Rate-limit & audit each method as if it were a tool call so abuse
    # against tools/list (cheap) and tools/call (expensive) both count.
    audit_tool = params.get("name", method) if method == "tools/call" else method
    if not isinstance(audit_tool, str):
        audit_tool = method
    # For tools/call the meaningful params are the inner tool arguments
    # (e.g. the search query); for other methods the JSON-RPC params
    # themselves carry useful detail. audit.py sanitises to an
    # allowlist before storing, so passing the raw dict is safe.
    if method == "tools/call" and isinstance(params.get("arguments"), dict):
        audit_params: dict[str, Any] = params["arguments"]
    else:
        audit_params = params or {}

    try:
        await enforce_rate_limit(request=request, auth=auth, tool_name=audit_tool)
    except HTTPException as exc:
        emit_audit(
            request=request,
            auth=auth,
            org_id=auth.org.id,
            token_id=auth.token_id,
            tool_name=audit_tool,
            transport="sse",
            params=audit_params,
            status_code=exc.status_code,
        )
        return JSONResponse(
            _rpc_error(req_id, _INTERNAL_ERROR, exc.detail or "Rate limited"),
            status_code=exc.status_code,
        )

    try:
        result = await _dispatch(method, params, db, auth)
    except _RPCError as exc:
        emit_audit(
            request=request,
            auth=auth,
            org_id=auth.org.id,
            token_id=auth.token_id,
            tool_name=audit_tool,
            transport="sse",
            params=audit_params,
            status_code=status.HTTP_404_NOT_FOUND if exc.code == _METHOD_NOT_FOUND else 400,
        )
        return JSONResponse(_rpc_error(req_id, exc.code, exc.message))
    except Exception:
        logger.exception("mcp_remote_dispatch_failed", method=method)
        emit_audit(
            request=request,
            auth=auth,
            org_id=auth.org.id,
            token_id=auth.token_id,
            tool_name=audit_tool,
            transport="sse",
            params=audit_params,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return JSONResponse(_rpc_error(req_id, _INTERNAL_ERROR, "Internal error"), status_code=500)

    emit_audit(
        request=request,
        auth=auth,
        org_id=auth.org.id,
        token_id=auth.token_id,
        tool_name=audit_tool,
        transport="sse",
        params=audit_params,
        status_code=status.HTTP_200_OK,
    )
    return JSONResponse(_rpc_result(req_id, result))


# Keepalive interval for the GET SSE stream. Each heartbeat re-verifies
# the bearer token so a revoked / expired token drops the stream within
# the heartbeat window instead of lingering until the client reconnects.
_SSE_HEARTBEAT_SECONDS = 30


@router.get("/sse")
async def remote_mcp_sse(
    request: Request,
    auth: MCPAuthResult = Depends(verify_mcp_token),
) -> StreamingResponse:
    """SSE keepalive stream for server-initiated messages.

    We do not push notifications today, so this only emits heartbeats and
    serves to honour token revocation mid-flight: the per-heartbeat
    re-auth via ``verify_mcp_token`` closes the stream on 401.

    No ``Depends(get_db)`` here on purpose — the request-scoped session
    would pin a connection from the pool for the entire stream lifetime
    (potentially hours). The heartbeat opens its own ``AsyncSessionLocal``.
    """
    stream_id = str(uuid.uuid4())
    token_id = auth.token_id
    # Sustained DB outage must not look like mass-revocation. Cap
    # consecutive token-check failures and fail-open for liveness up to
    # that cap, then close cleanly so the client can reconnect.
    max_consecutive_check_failures = 3

    async def _token_still_valid() -> bool:
        if token_id is None:
            return True
        async with AsyncSessionLocal() as session:
            tok = await UserMCPTokenRepository(session).get_by_id(token_id)
        if tok is None:
            return False
        return tok.expires_at is None or tok.expires_at > datetime.now(UTC)

    async def _stream() -> AsyncIterator[bytes]:
        yield f": stream {stream_id} ready\n\n".encode()
        consecutive_failures = 0
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    still_valid = await _token_still_valid()
                    consecutive_failures = 0
                except Exception:
                    consecutive_failures += 1
                    logger.warning(
                        "mcp_remote_sse_token_check_failed",
                        stream_id=stream_id,
                        token_id=str(token_id) if token_id else None,
                        consecutive_failures=consecutive_failures,
                        exc_info=True,
                    )
                    if consecutive_failures >= max_consecutive_check_failures:
                        logger.error(
                            "mcp_remote_sse_close_after_repeated_check_failures",
                            stream_id=stream_id,
                            token_id=str(token_id) if token_id else None,
                        )
                        break
                    # Fail-open for liveness: don't close on a single blip.
                    still_valid = True
                if not still_valid:
                    logger.info(
                        "mcp_remote_sse_token_revoked_or_expired",
                        stream_id=stream_id,
                        token_id=str(token_id) if token_id else None,
                    )
                    break
                yield b": ping\n\n"
                await asyncio.sleep(_SSE_HEARTBEAT_SECONDS)
        except asyncio.CancelledError:
            raise
        finally:
            logger.debug("mcp_remote_sse_closed", stream_id=stream_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router", "REMOTE_TOOLS"]
