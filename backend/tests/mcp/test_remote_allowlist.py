# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Sanity tests for the remote-MCP read-only allowlist and rate-limit weights.

These run without the DB/HTTP client because the allowlist is a frozenset
and the rate-limit cost map is a plain dict — pure-Python behaviour the
rest of the security model rests on.
"""

import pytest

from app.mcp.rate_limit import TOOL_COSTS, _cost
from app.mcp.streamable import REMOTE_TOOLS


def test_remote_allowlist_is_exactly_the_documented_tools() -> None:
    """If this test fails, a tool was added/removed remotely — confirm the
    docs (MCP-REMOTE.md) + connect-panel UI snippet still match before
    updating the assertion."""
    # Compared against a plain set literal so ruff's SIM300 doesn't flag
    # the comparison as Yoda — frozenset == set is true iff elements match.
    expected = {
        "get_bud_context",
        "get_features",
        "list_design_systems",
        "get_design_system",
        "get_prompt",
    }
    assert set(REMOTE_TOOLS) == expected


@pytest.mark.parametrize(
    "blocked_tool",
    [
        "write_bud",  # write surface — must never be remote
        "get_team_context",  # team PII — must never be remote
        "code_impact",  # code-graph — internal scan use only
        "post_slack_message",  # external side-effect
        "write_bud_design",  # write surface
    ],
)
def test_blocked_tools_not_in_remote_allowlist(blocked_tool: str) -> None:
    """Internal-only tools must not leak through the remote endpoint."""
    assert blocked_tool not in REMOTE_TOOLS


def test_rate_limit_assigns_higher_cost_to_expensive_tools() -> None:
    """Pgvector / embedding tools must cost more than plain lookups so a
    single client can't drain the bucket on the cheap stuff."""
    assert _cost("get_features") > _cost("get_bud_context")
    assert _cost("write_bud") > _cost("get_bud_context")


def test_rate_limit_unknown_tool_defaults_to_unit_cost() -> None:
    """Unknown tool name shouldn't cost zero (free spam) or crash."""
    assert _cost("a_brand_new_tool_we_have_not_added_yet") == 1


def test_every_remote_tool_has_an_explicit_cost_weight() -> None:
    """Forgetting a cost entry for a remote tool would silently default it
    to 1 — fine for cheap reads, but easy to miss for expensive ones."""
    for tool in REMOTE_TOOLS:
        assert tool in TOOL_COSTS, f"Remote tool {tool!r} missing from TOOL_COSTS"
