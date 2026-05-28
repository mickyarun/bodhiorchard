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

"""Duplicate-detection simulator for Slack triage.

Bypasses retrieval (no DB, no embeddings) and exercises two paths
that decide whether a Slack request is a duplicate:

1. ``code`` mode — the code-level LLM verifier in
   ``app.services.slack_intake._verify_duplicate_with_llm`` (called
   from ``triage_session`` before the agent runs).
2. ``skill`` mode — the triage agent itself reading the
   ``slack-triage`` skill markdown, with pre-injected MCP results
   so the agent never has to hit the real ``check_feature_exists`` /
   ``get_bud_context`` tools.

Both paths can emit "already tracked in the product backlog", so
both need to be hardened against narrow-tweak-vs-broad-feature
false positives.

Run from ``backend/``:

    python scripts/simulate_duplicate_detection.py            # both
    python scripts/simulate_duplicate_detection.py code       # code only
    python scripts/simulate_duplicate_detection.py skill      # skill only

Exits 0 only if every scenario in every selected mode passes.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.bud import BUDStatus  # noqa: E402
from app.services.claude_runner import (  # noqa: E402
    NO_REPO_CONTEXT,
    ClaudeRunnerConfig,
    run_claude_code,
)
from app.services.json_parser import parse_json_response  # noqa: E402
from app.services.slack_intake import _verify_duplicate_with_llm  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "app" / "agents" / "skills" / "slack-triage.md"


@dataclass
class FakeBUD:
    """Duck-typed stand-in for ``BUDDocument`` — only the fields the verifier reads."""

    bud_number: int
    title: str
    requirements_md: str
    status: BUDStatus = BUDStatus.DEVELOPMENT


@dataclass
class FakeFeature:
    """Duck-typed stand-in for ``Feature`` — only the fields the verifier reads."""

    feature_title: str
    description: str


@dataclass
class Scenario:
    """One verifier test case with the expected verdict."""

    label: str
    request: str
    candidates: list[tuple[str, Any, float]]
    expected_verdict: str  # "match" or "no_match"
    expected_index: int | None = None  # 1-based; only meaningful on "match"


SCENARIOS: list[Scenario] = [
    # ── False positives we must reject ────────────────────────────
    Scenario(
        label="narrow icon tweak vs broad notifications feature (reported bug)",
        request="Change the notification icon to modern design ?",
        candidates=[
            (
                "feature",
                FakeFeature(
                    feature_title="Notifications",
                    description=(
                        "In-app and email notifications for assignments,"
                        " mentions, and status changes."
                    ),
                ),
                0.72,
            ),
        ],
        expected_verdict="no_match",
    ),
    Scenario(
        label="bug report vs parent feature",
        request="Login fails when password has special characters like & or #",
        candidates=[
            (
                "feature",
                FakeFeature(
                    feature_title="User authentication",
                    description=(
                        "Email/password login, JWT session, refresh tokens, password reset flow."
                    ),
                ),
                0.74,
            ),
        ],
        expected_verdict="no_match",
    ),
    Scenario(
        label="topic overlap, different scope (auth vs last-login display)",
        request="Show the last login time on the user profile page",
        candidates=[
            (
                "feature",
                FakeFeature(
                    feature_title="User authentication",
                    description=(
                        "Email/password login, JWT session, refresh tokens, password reset flow."
                    ),
                ),
                0.68,
            ),
        ],
        expected_verdict="no_match",
    ),
    Scenario(
        label="UI polish vs broad feature (button colour)",
        request="Make the Submit button on the BUD form blue instead of grey",
        candidates=[
            (
                "feature",
                FakeFeature(
                    feature_title="BUD authoring",
                    description=(
                        "Create, edit, and submit BUDs from the web UI"
                        " with markdown sections per stage."
                    ),
                ),
                0.66,
            ),
        ],
        expected_verdict="no_match",
    ),
    Scenario(
        label="completely unrelated request shares one topic word",
        request="Add support for importing Trello boards",
        candidates=[
            (
                "feature",
                FakeFeature(
                    feature_title="Notifications",
                    description=(
                        "In-app and email notifications for assignments,"
                        " mentions, and status changes."
                    ),
                ),
                0.62,
            ),
        ],
        expected_verdict="no_match",
    ),
    # ── True duplicates we must catch ─────────────────────────────
    Scenario(
        label="same capability, different wording (CSV export)",
        request="Add a CSV export for the users table in admin panel",
        candidates=[
            (
                "feature",
                FakeFeature(
                    feature_title="Export user list",
                    description=(
                        "Allow admins to download all users as CSV with"
                        " email, role, last-login columns."
                    ),
                ),
                0.81,
            ),
        ],
        expected_verdict="match",
        expected_index=1,
    ),
    Scenario(
        label="in-flight BUD covers same ask (dark mode)",
        request="Add a dark mode toggle to the settings page",
        candidates=[
            (
                "bud",
                FakeBUD(
                    bud_number=42,
                    title="Dark mode support across all screens",
                    requirements_md=(
                        "Add a theme toggle in user settings; persist preference;"
                        " apply Vuetify dark theme app-wide."
                    ),
                    status=BUDStatus.DEVELOPMENT,
                ),
                0.83,
            ),
        ],
        expected_verdict="match",
        expected_index=1,
    ),
    # ── Multi-candidate disambiguation ────────────────────────────
    Scenario(
        label="multiple candidates — pick the specific BUD, not the broad feature",
        request="Send a Slack DM when a BUD is assigned to me",
        candidates=[
            (
                "feature",
                FakeFeature(
                    feature_title="Notifications",
                    description=(
                        "In-app and email notifications for assignments,"
                        " mentions, and status changes."
                    ),
                ),
                0.71,
            ),
            (
                "bud",
                FakeBUD(
                    bud_number=88,
                    title="Slack alerts for BUD assignment",
                    requirements_md=(
                        "When a BUD assignee changes, post a Slack DM to the"
                        " new assignee with link to the BUD."
                    ),
                    status=BUDStatus.DESIGN,
                ),
                0.86,
            ),
        ],
        expected_verdict="match",
        expected_index=2,
    ),
    # ── Degenerate inputs (real-world data quality issues) ────────
    Scenario(
        label="candidate with empty description (title-only)",
        request="Change the notification icon to modern design ?",
        candidates=[
            (
                "feature",
                FakeFeature(feature_title="Notifications", description=""),
                0.72,
            ),
        ],
        expected_verdict="no_match",
    ),
    Scenario(
        label="candidate with one-word description",
        request="Fix typo in onboarding welcome email",
        candidates=[
            (
                "feature",
                FakeFeature(feature_title="Onboarding", description="Onboarding."),
                0.69,
            ),
        ],
        expected_verdict="no_match",
    ),
    Scenario(
        label="multiple candidates, none truly match",
        request="Add keyboard shortcut to cycle between BUD tabs",
        candidates=[
            (
                "feature",
                FakeFeature(
                    feature_title="BUD authoring",
                    description=(
                        "Create, edit, and submit BUDs from the web UI"
                        " with markdown sections per stage."
                    ),
                ),
                0.64,
            ),
            (
                "feature",
                FakeFeature(
                    feature_title="BUD board",
                    description=(
                        "Kanban view of BUDs grouped by status with filters by assignee and title."
                    ),
                ),
                0.61,
            ),
        ],
        expected_verdict="no_match",
    ),
]


def _candidate_label(result: tuple[str, Any, float]) -> str:
    _, match, _ = result
    if hasattr(match, "feature_title"):
        return f"Feature {match.feature_title!r}"
    return f"BUD-{match.bud_number:03d} {match.title!r}"


def _matched_index(scenario: Scenario, result: tuple[str, Any, float]) -> int | None:
    return next(
        (i for i, c in enumerate(scenario.candidates, start=1) if c[1] is result[1]),
        None,
    )


async def _run_one(scenario: Scenario) -> tuple[bool, str]:
    result = await _verify_duplicate_with_llm(scenario.request, scenario.candidates)
    if scenario.expected_verdict == "no_match":
        if result is None:
            return True, "no_match (correct)"
        return False, f"matched {_candidate_label(result)} (expected no_match)"

    if result is None:
        return False, "no_match (expected match)"
    idx = _matched_index(scenario, result)
    if scenario.expected_index is not None and idx != scenario.expected_index:
        return False, f"matched index {idx}, expected {scenario.expected_index}"
    return True, f"match index {idx} (correct)"


# ── Skill-path simulator ──────────────────────────────────────────
#
# The triage agent reads ``slack-triage.md`` and decides on
# ``action: "exists"`` based on (a) MCP tool results and (b) the
# skill's scope-gate rubric. We pre-fabricate the tool result so
# the agent never has to actually call MCP — that isolates the
# rubric, exactly the lever we're tuning.


@dataclass
class SkillScenario:
    """A triage-agent run with one pre-injected duplicate-check result."""

    label: str
    request: str
    candidate_kind: str  # "feature" or "bud"
    candidate_title: str
    candidate_description: str
    candidate_score: float
    bud_number: int | None = None  # only for kind == "bud"
    bud_status: str | None = None
    expected_action: str = "no_match"  # "exists" or "no_match"


SKILL_SCENARIOS: list[SkillScenario] = [
    SkillScenario(
        label="icon tweak vs broad notifications feature (reported bug)",
        request="Change the notification icon to modern design ?",
        candidate_kind="feature",
        candidate_title="Notifications",
        candidate_description=(
            "In-app and email notifications for assignments, mentions, and status changes."
        ),
        candidate_score=0.72,
        expected_action="no_match",
    ),
    SkillScenario(
        label="bug report vs parent feature",
        request="Login fails when password contains & or # — server returns 500",
        candidate_kind="feature",
        candidate_title="User authentication",
        candidate_description=(
            "Email/password login, JWT session, refresh tokens, password reset flow."
        ),
        candidate_score=0.74,
        expected_action="no_match",
    ),
    SkillScenario(
        label="narrow change to existing feature scope",
        request="Show last login time on the user profile page",
        candidate_kind="feature",
        candidate_title="User authentication",
        candidate_description=(
            "Email/password login, JWT session, refresh tokens, password reset flow."
        ),
        candidate_score=0.71,
        expected_action="no_match",
    ),
    SkillScenario(
        label="true duplicate — same capability",
        request="Add a CSV export for the users table in admin panel",
        candidate_kind="feature",
        candidate_title="Export user list",
        candidate_description=(
            "Allow admins to download all users as CSV with email, role, last-login columns."
        ),
        candidate_score=0.82,
        expected_action="exists",
    ),
    SkillScenario(
        label="true duplicate — in-flight BUD",
        request="Add a dark mode toggle to the settings page",
        candidate_kind="bud",
        candidate_title="Dark mode support across all screens",
        candidate_description=(
            "Add a theme toggle in user settings; persist preference;"
            " apply Vuetify dark theme app-wide."
        ),
        candidate_score=0.85,
        bud_number=42,
        bud_status="development",
        expected_action="exists",
    ),
    SkillScenario(
        label="UI polish vs broad feature",
        request="Make the Submit button on the BUD form blue instead of grey",
        candidate_kind="feature",
        candidate_title="BUD authoring",
        candidate_description=(
            "Create, edit, and submit BUDs from the web UI with markdown sections per stage."
        ),
        candidate_score=0.68,
        expected_action="no_match",
    ),
]


_SKILL_PROMPT = """You are running a Slack triage. Use the rules in the
attached ``slack-triage`` skill.

For this simulation the duplicate-check tools have ALREADY been called
and returned the candidate below. DO NOT call any tools — treat this
block as the exact tool response.

CANDIDATE:
- kind: {kind}
- title: {title}{bud_extra}
- description: {description}
- score: {score:.2f} ({match_strength})

Apply Step 1's scope gate against the user request, then output ONE
JSON object — nothing else. Choose between:
- {{"action": "exists", "data": {{"kind": "...", "title": "...", ...}}}}
- {{"action": "question", "data": {{"message": "..."}}}}
- {{"action": "summary", "data": {{...}}}}

User request:
\"\"\"{request}\"\"\"
"""


def _build_skill_prompt(sc: SkillScenario) -> str:
    bud_extra = ""
    if sc.candidate_kind == "bud":
        bud_extra = f"\n- bud_number: {sc.bud_number}\n- status: {sc.bud_status}"
    match_strength = "strong" if sc.candidate_score >= 0.70 else "partial"
    return _SKILL_PROMPT.format(
        kind=sc.candidate_kind,
        title=sc.candidate_title,
        bud_extra=bud_extra,
        description=sc.candidate_description,
        score=sc.candidate_score,
        match_strength=match_strength,
        request=sc.request,
    )


async def _run_skill_scenario(sc: SkillScenario) -> tuple[bool, str]:
    config = ClaudeRunnerConfig(
        max_turns=1,
        timeout_seconds=90,
        system_prompt_files=[str(SKILL_PATH)],
        mcp=None,
    )
    result = await run_claude_code(
        prompt=_build_skill_prompt(sc),
        working_dir=NO_REPO_CONTEXT,
        config=config,
    )
    if not result.success:
        return False, f"runner error: {result.error}"

    parsed = parse_json_response(result.output)
    if not isinstance(parsed, dict):
        return False, f"unparsable output: {result.output[:200]!r}"
    action = parsed.get("action")
    got = "exists" if action == "exists" else "no_match"
    ok = got == sc.expected_action
    return ok, f"got action={action!r} (expected {sc.expected_action})"


async def _run_code_suite() -> int:
    print(f"\n── CODE-VERIFIER mode ({len(SCENARIOS)} scenarios) ──\n")
    results: list[tuple[str, bool, str]] = []
    for sc in SCENARIOS:
        try:
            ok, note = await _run_one(sc)
        except Exception as exc:  # noqa: BLE001 — simulator surfaces all errors
            ok, note = False, f"error: {exc!r}"
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {sc.label}\n        → {note}\n")
        results.append((sc.label, ok, note))

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"code mode: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


async def _run_skill_suite() -> int:
    print(f"\n── SKILL mode ({len(SKILL_SCENARIOS)} scenarios) ──\n")
    results: list[tuple[str, bool, str]] = []
    for sc in SKILL_SCENARIOS:
        try:
            ok, note = await _run_skill_scenario(sc)
        except Exception as exc:  # noqa: BLE001 — simulator surfaces all errors
            ok, note = False, f"error: {exc!r}"
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {sc.label}\n        → {note}\n")
        results.append((sc.label, ok, note))

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"skill mode: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


async def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode not in {"code", "skill", "both"}:
        print(f"unknown mode {mode!r} — expected code, skill, or both")
        return 2

    rc = 0
    if mode in {"code", "both"}:
        rc |= await _run_code_suite()
    if mode in {"skill", "both"}:
        rc |= await _run_skill_suite()
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
