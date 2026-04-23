# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the AI-PERT estimation prompt builder + agent profile resolver.

The prompt has a calibration role (anchoring the LLM's day-count scale) and
a configurability role (naming the AI coding agent from per-org config).
Both are exercised here without spinning up the LLM subprocess.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.estimation_llm import build_estimation_prompt
from app.services.org_settings import get_ai_agent_profile


def _stub_bud(
    requirements_md: str = "## PRD\nA short PRD.",
    tech_spec_md: str | None = None,
) -> SimpleNamespace:
    """Minimal BUDDocument-shaped stub. The prompt builder reads attributes
    only — no SQLAlchemy session needed."""
    return SimpleNamespace(
        requirements_md=requirements_md,
        tech_spec_md=tech_spec_md,
        impacted_repos=[],
        designs=[],
        qa_automation_cases=[],
        qa_manual_cases=[],
    )


_BACKLOG = {"queue_depth": 0, "assignee_workload": 0}
_PHASES = ["bud", "design", "development", "testing"]


# ── get_ai_agent_profile ────────────────────────────────────────


def test_agent_profile_defaults_to_claude_code_when_config_missing() -> None:
    assert get_ai_agent_profile(None)["name"] == "Claude Code"
    assert get_ai_agent_profile({})["name"] == "Claude Code"
    assert get_ai_agent_profile({"llm": {}})["name"] == "Claude Code"


def test_agent_profile_unknown_preset_falls_back_to_claude_code() -> None:
    profile = get_ai_agent_profile({"llm": {"preset": "not-a-real-agent"}})
    assert profile["name"] == "Claude Code"


@pytest.mark.parametrize(
    ("preset", "expected_name"),
    [
        ("claude-code", "Claude Code"),
        ("ollama", "Local LLM"),
        ("cloud", "Cloud LLM"),
        ("codex", "Codex"),
    ],
)
def test_agent_profile_known_presets(preset: str, expected_name: str) -> None:
    profile = get_ai_agent_profile({"llm": {"preset": preset}})
    assert profile["name"] == expected_name
    assert profile["hint"]  # Non-empty hint for every shipped preset.


# ── build_estimation_prompt ─────────────────────────────────────


def test_prompt_names_configured_agent_not_hardcoded_claude() -> None:
    """Switching the org's preset to ollama must replace the agent name in
    the prompt — guards against future hardcoding regressions."""
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
        org_config={"llm": {"preset": "ollama"}},
    )
    assert "Local LLM" in prompt
    assert "Claude Code" not in prompt


def test_prompt_default_org_config_uses_claude_code() -> None:
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
        org_config=None,
    )
    assert "Claude Code" in prompt


def test_prompt_includes_calibration_anchor_table() -> None:
    """Without the table the LLM regresses to ~M=2 days for everything;
    its presence is the primary fix for the over-estimation drift."""
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
    )
    assert "Calibration anchor" in prompt
    assert "complexity 1" in prompt
    assert "complexity 5" in prompt


def test_prompt_interpolates_heuristic_complexity() -> None:
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=4,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
    )
    assert "Heuristic complexity from BUD signals: 4/5" in prompt


def test_prompt_drops_seductive_numeric_example() -> None:
    """The old prompt's example (development M=2, testing M=1) acted as
    an anchoring prior. The new schema example must use placeholders, not
    concrete numbers, so the LLM has no example day count to copy."""
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
    )
    # The reply-format example must not contain literal day counts that
    # the LLM can latch onto; placeholders are the contract.
    assert '"M": 2' not in prompt
    assert '"M": 1' not in prompt
    assert "<num>" in prompt


def test_prompt_agent_line_precedes_prd_block() -> None:
    """The productivity hint must come before the (potentially 20K char)
    PRD content, otherwise the model has already calibrated upward by the
    time it reads it."""
    long_prd = "## PRD\n" + ("- requirement line\n" * 500)
    prompt = build_estimation_prompt(
        bud=_stub_bud(requirements_md=long_prd),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
    )
    agent_idx = prompt.index("Claude Code")
    prd_idx = prompt.index("PRD content:")
    assert agent_idx < prd_idx


def test_prompt_permits_near_zero_estimates_for_na_phases() -> None:
    """Without explicit permission, the model floors every phase at ~0.5d,
    creating a structural minimum of 4d for an 8-phase lifecycle even when
    several phases are essentially N/A."""
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=1,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
    )
    assert "essentially N/A" in prompt
    assert "0.1" in prompt


# ── Phase B: capacity context + effort/wall-clock + bugs ─────────


def test_prompt_unit_is_focused_effort_not_wall_clock() -> None:
    """The LLM must estimate effort, not wall-clock — the engine
    converts via the capacity divisor. This line is the contract that
    prevents double-counting capacity (once in the LLM's pessimism,
    once in the post-MC divisor)."""
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
    )
    assert "focused effort" in prompt
    assert "do not pre-discount" in prompt


def test_prompt_renders_capacity_summary_when_supplied() -> None:
    """Capacity tuples must surface in the prompt so the LLM can see
    why dates might shift. Missing/empty summary → no block (callers
    that haven't migrated keep working)."""
    summary = [
        ("designer", 0.40, "60% loaded"),
        ("developer", 0.70, "30% loaded"),
    ]
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
        capacity_summary=summary,
    )
    assert "Team capacity right now" in prompt
    assert "designer: 0.40 (60% loaded)" in prompt
    assert "developer: 0.70 (30% loaded)" in prompt


def test_prompt_omits_capacity_block_when_summary_empty() -> None:
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
        capacity_summary=None,
    )
    assert "Team capacity right now" not in prompt


def test_prompt_renders_open_bug_count_when_present() -> None:
    prompt = build_estimation_prompt(
        bud=_stub_bud(),
        complexity=2,
        backlog_ctx=_BACKLOG,
        skill_ctx=None,
        historical_ctx="",
        remaining_phases=_PHASES,
        bug_context={"open_bug_count": 3},
    )
    assert "Open bugs against this BUD: 3" in prompt


def test_prompt_omits_bug_line_when_zero_or_missing() -> None:
    """Zero bugs and missing bug context must both produce no line —
    avoids a noisy 'Open bugs against this BUD: 0' for the common case."""
    for ctx in (None, {}, {"open_bug_count": 0}):
        prompt = build_estimation_prompt(
            bud=_stub_bud(),
            complexity=2,
            backlog_ctx=_BACKLOG,
            skill_ctx=None,
            historical_ctx="",
            remaining_phases=_PHASES,
            bug_context=ctx,
        )
        assert "Open bugs against this BUD" not in prompt
