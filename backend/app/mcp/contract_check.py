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


def _extract_all_string_key_reads(handler: Callable[..., Any]) -> set[str] | None:
    """Return every string-literal key the handler accesses on ANY object.

    Broader than ``_extract_param_reads`` — used to verify nested-shape
    schema keys (e.g. ``op.get("canonical_synth_id")`` inside an array
    item) actually get read. Walks ``<anything>.get("X")`` and
    ``<anything>["X"]`` patterns regardless of the target variable.

    Also follows imports: the handler often delegates op-shape
    validation to a sibling helper (e.g. ``_validate_op_shape``) in the
    same module, so we collect literal keys from every function in the
    handler's module rather than just the handler body.

    Returns ``None`` when the handler's source can't be parsed.
    """
    try:
        # Walk the entire module the handler lives in — handlers commonly
        # delegate per-op validation to a sibling helper in the same file.
        module = inspect.getmodule(handler)
        if module is None:
            return None
        source = inspect.getsource(module)
    except (OSError, TypeError):
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    reads: set[str] = set()
    for node in ast.walk(tree):
        # <anything>.get("X", default?)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            reads.add(node.args[0].value)
        # <anything>["X"]
        elif isinstance(node, ast.Subscript):
            key_node = node.slice
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                reads.add(key_node.value)
    return reads


def _collect_nested_item_property_keys(schema: dict[str, Any]) -> set[str]:
    """Collect every property key declared inside an ``array → items.object`` shape.

    The top-level ``check_mcp_contracts`` already validates top-level
    properties. This helper recurses into ``properties[*].items.properties``
    chains so a schema like ``ops: [{canonical_synth_id, …}]`` exposes
    its nested keys for the handler-read check.
    """
    keys: set[str] = set()
    properties = schema.get("properties") or {}
    for prop_schema in properties.values():
        if not isinstance(prop_schema, dict):
            continue
        if prop_schema.get("type") == "array":
            items = prop_schema.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                nested_props = items.get("properties") or {}
                keys.update(nested_props.keys())
                keys.update(_collect_nested_item_property_keys(items))
        elif prop_schema.get("type") == "object":
            keys.update(_collect_nested_item_property_keys(prop_schema))
    return keys


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
        schema_props: set[str] = set((tool.input_schema.get("properties") or {}).keys())
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

        # 3. Nested item shapes (e.g. ``ops: [{canonical_synth_id, ...}]``)
        # must have every declared key actually read by the handler or
        # one of its sibling helpers in the same module. Catches the
        # ``apply_feature_merge_plan: canonical_id vs canonical_synth_id``
        # drift the top-level check missed.
        nested_keys = _collect_nested_item_property_keys(tool.input_schema)
        if nested_keys:
            broad_reads = _extract_all_string_key_reads(handler)
            if broad_reads is None:
                logger.info(
                    "mcp_contract_check_nested_skipped",
                    tool=tool.name,
                    reason="handler module source unavailable",
                )
            else:
                unused_nested = nested_keys - broad_reads
                if unused_nested:
                    problems.append(
                        f"{tool.name}: schema declares nested-item keys the "
                        f"handler module never reads (likely schema drift): "
                        f"{sorted(unused_nested)}"
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
