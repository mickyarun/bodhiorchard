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

"""Runs MCP tools in-process for the Ollama provider.

The CLI providers reach MCP the long way: CLI subprocess -> stdio JSON-RPC ->
``stdio_bridge`` subprocess -> HTTP -> FastAPI -> token auth -> dispatch. With
no CLI there is no subprocess, so all of that collapses into a dict lookup and
an ``await``. Nothing here mints a token: the token never reaches a handler
anyway — handlers take their org as an argument — so ``MCPAuthResult`` is just
constructed. That also sidesteps the cross-process token problem, since
``_internal_tokens`` is a per-process dict.

Deliberately ignores ``REMOTE_TOOLS``: that allowlist exists to narrow what
*untrusted external* clients may call over ``/mcp/sse``. This loop is a trusted
in-process caller, like the scan pipeline, and honouring it would cut off
``search_bugs`` and ``check_feature_exists`` — the tools the intake sites need.
The caller's ``tool_names`` is the allowlist that applies here.
"""

import json
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.auth import MCPAuthResult
from app.mcp.server import AUTH_TOOL_HANDLERS, MCP_TOOLS, TOOL_HANDLERS

logger = structlog.get_logger(__name__)


class NoToolsRequestedError(ValueError):
    """A tool-using run named no tools."""


def build_tool_schemas(tool_names: list[str]) -> list[dict[str, Any]]:
    """Our MCP tool definitions in the shape Ollama's ``tools`` param expects.

    ``MCP_TOOLS`` already carries real JSON Schema with no root combinators, so
    ``input_schema`` transfers as ``parameters`` untouched.

    Raises on an empty ``tool_names``, rather than quietly offering none. The
    CLI path reads empty as "expose everything" (``stdio_bridge``), so a caller
    written against that meaning would otherwise get a model with no tools that
    answers in prose — and for agents whose whole output is MCP side effects,
    that reads as a clean success while nothing was written. Failing here is
    the difference between a visible error and a BUD that silently never
    changed. 29 tools is also far more than a small local model should be asked
    to choose between, so callers name what they need.
    """
    if not tool_names:
        raise NoToolsRequestedError(
            "This feature did not name the MCP tools it needs, so they cannot be offered."
        )
    wanted = set(tool_names)
    schemas = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in MCP_TOOLS
        if t.name in wanted
    ]
    missing = wanted - {t.name for t in MCP_TOOLS}
    if missing:
        # A typo'd name would otherwise just never be offered, and the model
        # would improvise around a tool it was never given.
        logger.warning("ollama_unknown_tools_requested", tools=sorted(missing))
    return schemas


def parse_tool_call(call: object) -> tuple[str, dict[str, Any]] | None:
    """Pull (name, arguments) out of one of the model's tool calls.

    Returns None for anything malformed. Never trust the shape a model
    produces: a bad element must skip that call, not kill the run.
    """
    if not isinstance(call, dict):
        return None
    fn = call.get("function")
    if not isinstance(fn, dict):
        return None
    name = fn.get("name")
    if not isinstance(name, str) or not name:
        return None
    args = fn.get("arguments")
    if isinstance(args, str):
        # Several Ollama-served models emit `arguments` as a JSON string rather
        # than an object. Coercing that to {} would run the tool with no
        # arguments — search_bugs with no query, update_bud with no fields —
        # which succeeds and returns something plausible instead of failing.
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            logger.warning("ollama_tool_args_unparseable", tool=name, raw=args[:200])
            return None
    return name, args if isinstance(args, dict) else {}


async def _reload_org_after_rollback(db: AsyncSession, auth: MCPAuthResult) -> None:
    """Re-load ``auth.org`` after a rollback so the next tool call can use it.

    ``rollback()`` expires every instance in the session — that's unconditional,
    unlike ``expire_on_commit``. The handlers read the org (``org.id`` at
    minimum) through plain attribute access, which on an expired instance means
    a lazy re-SELECT from sync code and therefore ``MissingGreenlet``. Without
    this, one failing tool call poisons every call after it: each subsequent
    tool dies on the org rather than on its own merits, the model is handed a
    wall of "backend error", and it gives up on an otherwise healthy run.

    Best-effort by design — a failure here must not escape and kill the run,
    since we are already on the path of reporting another failure to the model.
    """
    try:
        await db.refresh(auth.org)
    except Exception:
        logger.exception("ollama_org_reload_failed", org_id=str(auth.org.id))


async def dispatch_tool(
    db: AsyncSession, auth: MCPAuthResult, name: str, arguments: dict[str, Any]
) -> str:
    """Run one tool call and return its result as text for the model.

    Errors come back as text rather than raising: handlers already signal
    failure by returning ``{"error": ...}``, and the model needs to read the
    failure to recover from it. Ollama has no ``isError`` channel, so the
    distinction the HTTP transports draw does not exist here — a deliberate
    divergence, not an oversight.
    """
    # Two handler tables with different second arguments: the auth ones need
    # the whole MCPAuthResult (some check auth.user), the rest just the org.
    auth_handler = AUTH_TOOL_HANDLERS.get(name)
    handler = TOOL_HANDLERS.get(name)
    if auth_handler is None and handler is None:
        # The model invented a tool. Tell it so, rather than failing the run.
        logger.warning("ollama_tool_not_found", tool=name)
        return json.dumps({"error": f"No such tool: {name}"})

    try:
        if auth_handler is not None:
            result = await auth_handler(db, auth, arguments)
        elif handler is not None:
            result = await handler(db, auth.org, arguments)
    except Exception as exc:
        # Nothing upstream catches handler crashes on this path — the HTTP
        # transports rely on FastAPI for that. Surfacing the failure to the
        # model beats killing a run over one bad call.
        #
        # Roll back first: a handler that failed mid-flush leaves the session
        # in a state where every later statement — including the loop's own
        # commit — raises PendingRollbackError, turning one bad tool call into
        # a crash that escapes run() and breaks its contract of always
        # returning a ClaudeRunResult.
        await db.rollback()
        await _reload_org_after_rollback(db, auth)
        logger.exception("ollama_tool_failed", tool=name, error=str(exc))
        return json.dumps({"error": f"{name} failed: {exc}"})

    is_error = isinstance(result, dict) and "error" in result
    logger.info("ollama_tool_called", tool=name, ok=not is_error)
    return json.dumps(result, default=str)
