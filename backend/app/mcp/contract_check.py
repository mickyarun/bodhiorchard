# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Static contract check: every MCP tool's schema ↔ handler must agree.

Catches the class of bug that made ``write_bud`` silently clobber BUDs
for months: schema declared ``content`` as required, handler read
``content``, but the prompt steered Claude to send ``requirements_md``
and nothing caught the drift. Hard-failing at startup turns any future
schema/handler mismatch into a visible deploy error instead of silent
data loss in production.

The check inspects each registered MCP tool's handler AST for literal
``params.get("key")`` / ``params["key"]`` reads, then verifies:

* **Every required schema field** is read by the handler. Otherwise the
  agent will send a value the handler ignores.
* **Every key the handler reads is declared in the schema.** Otherwise
  Claude won't know the field exists and won't send it (the case
  flagged by ``bud_number`` reads that never appeared in the schema).

Handlers that access params dynamically (via a variable key, or
``**kwargs``-style unpacking) are skipped with a warning — the check
is best-effort AST analysis, not a runtime interceptor.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _extract_param_reads(handler: Callable[..., Any]) -> set[str] | None:
    """Return the set of literal keys ``handler`` reads from ``params``.

    Walks the handler's source via ``ast`` looking for
    ``params.get("X")`` and ``params["X"]`` patterns. Returns ``None``
    when the handler does something dynamic we can't analyze
    statically (the caller then skips this tool with a warning).
    """
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):
        return None

    # Dedent so ``ast.parse`` accepts it regardless of method indent.
    source = inspect.cleandoc(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    reads: set[str] = set()
    dynamic = False

    for node in ast.walk(tree):
        # params.get("X", default?)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "params"
        ):
            if node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, str):
                    reads.add(node.args[0].value)
            else:
                dynamic = True
        # params["X"]
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "params"
        ):
            key_node = node.slice
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                reads.add(key_node.value)
            else:
                dynamic = True

    if dynamic and not reads:
        # Purely dynamic access — can't verify.
        return None
    # Mix of literal + dynamic access is still useful; surface what we found.
    return reads


def check_mcp_contracts() -> None:
    """Validate the schema ↔ handler contract for every registered MCP tool.

    Raises:
        RuntimeError: when any tool has a schema/handler mismatch that
            would cause the same class of bug as ``write_bud`` did.
    """
    # Imported lazily so the module is cheap to import from main's lifespan.
    from app.mcp.server import (
        AUTH_TOOL_HANDLERS,
        MCP_TOOLS,
        TOOL_HANDLERS,
    )

    problems: list[str] = []
    skipped: list[str] = []

    for tool in MCP_TOOLS:
        schema_props: set[str] = set(
            (tool.input_schema.get("properties") or {}).keys()
        )
        required: set[str] = set(tool.input_schema.get("required") or [])

        handler = TOOL_HANDLERS.get(tool.name) or AUTH_TOOL_HANDLERS.get(tool.name)
        if handler is None:
            problems.append(f"{tool.name}: declared in MCP_TOOLS but no handler registered")
            continue

        reads = _extract_param_reads(handler)
        if reads is None:
            skipped.append(tool.name)
            continue

        # 1. Every required schema field must be read.
        unused_required = required - reads
        if unused_required:
            problems.append(
                f"{tool.name}: schema lists these as required but handler never "
                f"reads them: {sorted(unused_required)}"
            )

        # 2. Every literal key the handler reads must appear in the schema
        # (otherwise Claude won't know to send it).
        undeclared_reads = reads - schema_props
        if undeclared_reads:
            problems.append(
                f"{tool.name}: handler reads these keys but they are not "
                f"declared in the schema (Claude won't send them): "
                f"{sorted(undeclared_reads)}"
            )

    if skipped:
        logger.info(
            "mcp_contract_check_skipped",
            tools=skipped,
            reason="dynamic param access — AST check can't verify statically",
        )

    if problems:
        msg = "MCP schema↔handler contract check failed:\n  - " + "\n  - ".join(problems)
        logger.error("mcp_contract_check_failed", problems=problems)
        raise RuntimeError(msg)

    logger.info(
        "mcp_contract_ok",
        tools_checked=len(MCP_TOOLS) - len(skipped),
        tools_skipped=len(skipped),
    )
