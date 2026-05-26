# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Guard rail: MCP tool schemas must stay compatible with the Anthropic API.

The Anthropic Tools API rejects ``oneOf`` / ``allOf`` / ``anyOf`` at the
root of a tool's ``input_schema`` with::

    API Error: 400 tools.N.custom.input_schema:
    input_schema does not support oneOf, allOf, or anyOf at the top level

JSON Schema and the MCP protocol both accept these combinators at any
depth, so the issue can sit dormant on a deferred tool until the first
agent flow actually selects it. These tests fail at CI time instead, so
the next contributor cannot reintroduce the pattern.

Both transports are covered:

* ``MCP_TOOLS`` (``app.mcp.server``) — internal MCP server used by our
  own agents and the Claude CLI subprocess.
* ``_REMOTE_TOOL_SCHEMAS`` (``app.mcp.streamable``) — remote ``/mcp/sse``
  endpoint exposed to external BYO-AI clients.

Constraint expression belongs in:

* the tool ``description`` (LLM-readable), and
* the handler (runtime enforcement) — typically a single guard call that
  returns a structured ``missing_*`` / ``bad_*`` error.

Never in the schema root.
"""

from typing import Any

import pytest

from app.mcp.server import MCP_TOOLS
from app.mcp.streamable import _REMOTE_TOOL_SCHEMAS

_FORBIDDEN_ROOT_KEYS = ("oneOf", "allOf", "anyOf")


@pytest.mark.parametrize(
    ("tool_name", "schema"),
    [(t.name, t.input_schema) for t in MCP_TOOLS],
    ids=[t.name for t in MCP_TOOLS],
)
def test_internal_tool_schema_has_no_root_combinators(
    tool_name: str, schema: dict[str, Any]
) -> None:
    offenders = [k for k in _FORBIDDEN_ROOT_KEYS if k in schema]
    assert not offenders, (
        f"Tool {tool_name!r} (app.mcp.server.MCP_TOOLS) has root-level"
        f" schema combinators {offenders!r}. The Anthropic Tools API"
        " rejects these at the input_schema root. Move the constraint"
        " into the handler's runtime validation and document it in the"
        " tool description."
    )


@pytest.mark.parametrize(
    ("tool_name", "schema"),
    [(t["name"], t["inputSchema"]) for t in _REMOTE_TOOL_SCHEMAS],
    ids=[t["name"] for t in _REMOTE_TOOL_SCHEMAS],
)
def test_remote_tool_schema_has_no_root_combinators(
    tool_name: str, schema: dict[str, Any]
) -> None:
    offenders = [k for k in _FORBIDDEN_ROOT_KEYS if k in schema]
    assert not offenders, (
        f"Tool {tool_name!r} (app.mcp.streamable._REMOTE_TOOL_SCHEMAS)"
        f" has root-level schema combinators {offenders!r}. The Anthropic"
        " Tools API rejects these at the input_schema root. Move the"
        " constraint into the handler's runtime validation and document"
        " it in the tool description."
    )
