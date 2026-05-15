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

"""Prompt builders for BUD agent tasks.

Each builder takes a BUD, skill config, org_id, and db session,
returning (prompt_string, optional_working_dir). The prompt is
passed to Claude Code CLI for execution.
"""

import json
import uuid as uuid_mod
from pathlib import Path
from typing import Any

import structlog

from app.models.bud import BUDDocument
from app.repositories.feature_reads import FeatureReadRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.bud_agent_context import (
    format_code_locations_section,
    load_bud_agent_context,
)
from app.services.embedding_service import embedding_service
from app.services.prompt_builder import build_prd_prompt as _build_prd
from app.services.skill_loader import Skill

logger = structlog.get_logger(__name__)


async def build_prd_prompt(
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid_mod.UUID,
    db: Any,
) -> tuple[str, str | None]:
    """Build PRD enrichment prompt from triage context.

    Adds two grounding sections that kill the LLM's tendency to write
    against generic / hallucinated content: real tracked-repo names,
    and a top-K semantic prefetch of likely-related existing features.
    Both are lightweight (<1 KB combined) compared to dumping the
    full feature list, which can run to hundreds of rows per org.
    """

    meta = bud.metadata_ or {}
    session_id = meta.get("triage_session_id")

    triage_context: dict[str, Any] = {}
    if session_id:
        from app.models.triage_session import TriageSession

        session = await db.get(TriageSession, uuid_mod.UUID(session_id))
        if session:
            triage_context = session.triage_context or {}

    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    repo_summaries = await _build_repo_summaries(repo_repo)

    brief = _build_pm_brief(bud, triage_context)
    candidate_features = await _build_pm_candidate_features(db, org_id=org_id, brief=brief)

    prompt = await _build_prd(
        skill_name=skill.slug,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        triage_context=triage_context,
        requirements_md=bud.requirements_md or "",
        org_id=org_id,
        db=db,
        repo_summaries=repo_summaries,
        candidate_features=candidate_features,
    )
    return prompt, None


async def _build_repo_summaries(repo_repo: Any) -> list[str]:
    """Render active tracked repos as compact markdown bullets.

    Naming them in the prompt is what stops the PM agent from inventing
    product names — embedding search alone can't fix a hallucination
    that originates from missing context.
    """
    repos = await repo_repo.list_active()
    summaries: list[str] = []
    for repo in repos:
        layer = repo.repo_layer.value if repo.repo_layer is not None else None
        line = f"- **{repo.name}**" + (f" — layer={layer}" if layer else "")
        summaries.append(line)
    return summaries


def _build_pm_brief(bud: BUDDocument, triage_context: dict[str, Any]) -> str:
    """Concatenate the BUD signals an embedding-search query should see.

    Combines title, current draft, and triage context into a single
    string capped at 4 KB — the same length cap the embedding service
    applies for feature content, so we stay within the model's
    sensitive range.
    """
    parts: list[str] = [bud.title]
    if bud.requirements_md:
        parts.append(bud.requirements_md)
    if triage_context:
        parts.append(json.dumps(triage_context))
    return "\n\n".join(parts)[:4000]


async def _build_pm_candidate_features(
    db: Any,
    *,
    org_id: uuid_mod.UUID,
    brief: str,
    limit: int = 8,
) -> list[tuple[str, str, float]]:
    """Top-K existing features ranked by cosine distance to the brief.

    Returns ``(feature_id_str, title, similarity)`` where ``similarity``
    is ``1 - distance`` so higher = closer. Defensive: returns ``[]``
    when the brief is empty or embedding/search fails — the prompt
    still works without prefetch, the agent can fall back to
    ``get_features``.
    """
    if not brief.strip():
        return []
    try:
        vec = await embedding_service.embed(brief)
        feature_repo = FeatureReadRepository(db, org_id=org_id)
        hits = await feature_repo.semantic_search(vec, limit=limit, only_active=True)
    except Exception as exc:  # noqa: BLE001 — defensive: prefetch is opt-in context
        logger.warning("pm_candidate_features_failed", error=str(exc))
        return []
    # pgvector ``cosine_distance`` is in [0, 2]; clamp the inverted
    # similarity to non-negative so the prompt never renders
    # ``similarity -0.13`` for pairs worse than orthogonal.
    return [
        (str(feat.id), feat.feature_title, max(0.0, 1.0 - distance)) for feat, distance in hits
    ]


async def build_tech_arch_prompt(
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid_mod.UUID,
    db: Any,
) -> tuple[str, str | None]:
    """Build tech architecture prompt with design context and repo info.

    Augments the existing repo/design context with an "Existing code to
    read before planning" section sourced from every feature the BUD is
    linked to — surfacing all layers of ``code_locations`` so the
    planner can call ``code_context`` / ``code_impact`` against the
    right files instead of guessing.
    """
    from app.repositories.design_system import DesignSystemRefRepository

    bud_ref = f"BUD-{bud.bud_number:03d}"

    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    repo_triples = await repo_repo.get_active_id_path_name()
    repo_pairs = [(path, name) for _, path, name in repo_triples]
    working_dir = repo_triples[0][1] if repo_triples else None

    design_directive = _build_design_mcp_directive(bud, purpose="planning")

    ds_repo = DesignSystemRefRepository(db, org_id=org_id)
    has_design_system = bool(await ds_repo.get_default())

    repo_context = _build_repo_context(repo_pairs)

    ctx = await load_bud_agent_context(db, bud_id=bud.id, org_id=org_id)
    linked_section = format_code_locations_section(
        ctx.linked_features,
        heading="## Existing code to read before planning",
        instruction=(
            "Before proposing changes, call `code_context` / `code_impact` on "
            "the symbols in these files to confirm current behaviour. Your "
            "`impacted_repos` JSON fence MUST include every repo whose code "
            "is listed above."
        ),
    )

    prompt = (
        f"Generate a concise tech spec for {bud_ref}: {bud.title}.\n\n"
        f"## Requirements\n\n{bud.requirements_md or ''}\n"
    )
    if design_directive:
        prompt += design_directive
    if has_design_system:
        prompt += (
            "\n## Design System\n\n"
            "Use the `get_design_system` MCP tool to fetch design tokens. "
            "Do NOT hardcode values — reference the design system.\n"
        )
    if linked_section:
        prompt += "\n" + linked_section
    if repo_context:
        prompt += repo_context

    # Static instructions come from the skill row (admin-editable via
    # Settings → Agent Prompts). The Python builder only owns per-BUD
    # data (requirements, repos, designs, linked features) and the
    # data-driven JSON fence requirement that lists the BUD's actual
    # impacted_repos by name.
    prompt += f"\n---\n\n{skill.prompt}\n"
    prompt += _build_impacted_repos_fence(bud, repo_pairs)

    return prompt, working_dir


async def build_code_review_prompt(
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid_mod.UUID,
    db: Any,
) -> tuple[str, str | None]:
    """Build code review prompt with repo locations and PR-aware diffs.

    When the BUD has linked features, prepends a "Linked feature
    surfaces" section listing the files those features OWN — the
    reviewer uses this to flag scope-creep (PR touches files outside
    any linked feature) and missing-coverage (linked feature has files
    not touched by the PR but the requirement implies they should be).
    """
    from app.repositories.dev_activity import DevActivityLogRepository
    from app.repositories.pull_request import PullRequestRepository

    bud_ref = f"BUD-{bud.bud_number:03d}"
    meta = bud.metadata_ or {}
    confirmed_repos = meta.get("confirmed_repos", [])

    activity_repo = DevActivityLogRepository(db, org_id=org_id)
    last_shas = await activity_repo.get_last_sha_per_repo(bud.id)

    pr_repo = PullRequestRepository(db, org_id=org_id)
    linked_prs = await pr_repo.list_for_bud(bud.id)
    pr_branches: dict[str, str] = {}
    for pr in linked_prs:
        if pr.state.value == "open":
            repo_short = pr.github_repo_full_name.split("/")[-1]
            pr_branches[repo_short] = pr.head_branch

    repo_sections, working_dir = _build_repo_diff_sections(
        confirmed_repos,
        last_shas,
        pr_branches,
    )

    if not repo_sections:
        raise ValueError("No confirmed repos with commits for code review")

    repo_list = "\n".join(repo_sections)

    design_refs = _build_design_mcp_directive(bud, purpose="reviewing")

    ctx = await load_bud_agent_context(db, bud_id=bud.id, org_id=org_id)
    linked_section = format_code_locations_section(
        ctx.linked_features,
        heading="## Linked feature surfaces",
        instruction=(
            "Cross-reference your `git diff` against these paths:\n"
            "- Files touched by the PR that are NOT in any linked feature's "
            "code_locations → flag as **scope-creep** (warning).\n"
            "- Files listed above that the requirement implies should change "
            "but the PR did NOT touch → flag as **missing-coverage** (warning).\n"
            "- If a linked feature's expected file is touched, that's the "
            "happy path — no flag needed."
        ),
    )

    # Static review instructions (scope, rules, workflow, checklist,
    # output schema) come from the ``code-reviewer`` skill row in DB.
    # The Python builder owns only per-BUD data: BUD reference, repo
    # diff sections, design references, linked-feature surfaces.
    prompt = (
        f"Code review for {bud_ref}: {bud.title}.\n\n"
        f"## Repos\n\n{repo_list}\n\n"
        f"{design_refs}"
        f"{linked_section}"
        f"---\n\n{skill.prompt}\n"
    )

    return prompt, working_dir


async def build_testing_prompt(
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid_mod.UUID,
    db: Any,
) -> tuple[str, str | None]:
    """Build QA testing prompt with repo locations and commit refs.

    Reads the org's QA automation settings (``org.config.qa``) so the
    agent targets the right framework, or produces manual-only cases when
    the org has automation disabled. See ``org_settings.get_qa_settings``.
    """
    from app.repositories.dev_activity import DevActivityLogRepository
    from app.repositories.organization import OrganizationRepository
    from app.services.org_settings import get_qa_settings

    bud_ref = f"BUD-{bud.bud_number:03d}"
    meta = bud.metadata_ or {}
    confirmed_repos = meta.get("confirmed_repos", [])

    activity_repo = DevActivityLogRepository(db, org_id=org_id)
    last_shas = await activity_repo.get_last_sha_per_repo(bud.id)

    # Load org QA config. BUDDocument has no .organization relationship
    # (only an org_id FK), so we load the org explicitly.
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    qa = get_qa_settings(org.config if org else None)
    framework = qa.framework

    repo_sections, working_dir = _build_repo_diff_sections(
        confirmed_repos,
        last_shas,
        pr_branches={},
    )
    repo_list = "\n".join(repo_sections) if repo_sections else "(no repos confirmed)"

    draft_auto = meta.get("automation_test_plan_md", "")
    draft_manual = meta.get("manual_test_plan_md", "")

    draft_context = ""
    if draft_auto or draft_manual:
        draft_context = "\n## Draft Test Plans (from Code Review)\n\n"
        if draft_auto:
            draft_context += f"### Automation\n\n{draft_auto}\n\n"
        if draft_manual:
            draft_context += f"### Manual\n\n{draft_manual}\n\n"
        draft_context += (
            "Refine these drafts into structured test cases. Do not pad — improve precision.\n\n"
        )

    design_refs = _build_design_mcp_directive(bud, purpose="writing test cases")

    ctx = await load_bud_agent_context(db, bud_id=bud.id, org_id=org_id)
    linked_section = format_code_locations_section(
        ctx.linked_features,
        heading="## Linked feature surfaces (extend existing tests around these files)",
        instruction=(
            "For each file listed above, look for an adjacent test file (e.g. "
            "`tests/...test_<name>.py` next to `app/.../<name>.py`, or "
            "`<Component>.spec.ts` next to `<Component>.vue`). Prefer extending "
            "those existing tests over creating new files — match their fixture "
            "and assertion style. Only add new test files when no adjacent "
            "tests exist."
        ),
    )

    prompt = (
        f"You are generating structured test cases for {bud_ref}: {bud.title}.\n\n"
        f"## Repositories\n\n{repo_list}\n\n"
        f"{design_refs}"
        f"{linked_section}"
    )
    if draft_context:
        prompt += draft_context

    # Static instructions (rules, categories, workflow, output format)
    # come from the ``testing`` skill row in DB. Python only owns per-BUD
    # data (repos, designs, linked features, draft test plans) and the
    # org-level QA mode toggle that decides whether to emit automation
    # cases for ``framework`` or set ``automation_test_cases: []``.
    prompt += f"\n---\n\n{skill.prompt}\n"
    prompt += _build_qa_mode_block(qa.enabled, framework)

    return prompt, working_dir


def _build_qa_mode_block(enabled: bool, framework: str) -> str:
    """Per-org QA mode override appended after the skill's static body."""
    if enabled:
        return (
            "\n## QA Mode\n\n"
            f"`enabled` — write automation cases for **{framework}**. "
            "Gherkin scenarios that a developer can hand to Claude Code to "
            f"produce a working {framework} test file. Cover functional "
            "flows, negative paths, boundary values, regression checks.\n"
        )
    return (
        "\n## QA Mode\n\n"
        "`disabled` — this organization has automation off. Return "
        "`automation_test_cases: []` and cover the full test surface "
        "(functional, negative, boundary, regression, visual, accessibility) "
        "in manual cases. Each manual case must be executable by a human "
        "tester without an automation framework.\n"
    )


# ── Shared helpers ────────────────────────────────────────────────


def _build_repo_diff_sections(
    confirmed_repos: list[dict[str, Any]],
    last_shas: dict[str, str],
    pr_branches: dict[str, str],
) -> tuple[list[str], str | None]:
    """Build repo sections with diff commands (shared by code review & testing)."""
    sections: list[str] = []
    working_dir: str | None = None

    for repo_info in confirmed_repos:
        repo_path = repo_info.get("repo_path", "")
        repo_name = repo_info.get("repo_name", Path(repo_path).name)
        if not repo_path:
            continue
        if working_dir is None:
            working_dir = repo_path

        pr_branch = pr_branches.get(repo_name)
        if pr_branch:
            sections.append(
                f"- **{repo_name}**: `{repo_path}`\n"
                f"  - PR branch: `{pr_branch}`\n"
                f"  - First run: `git fetch origin {pr_branch}`\n"
                f"  - Diff command: `git diff main...origin/{pr_branch} --stat --patch`"
            )
        else:
            last_sha = last_shas.get(repo_path, "HEAD")
            develop_wt = Path(repo_path) / ".bodhiorchard" / "develop"
            diff_base = "develop" if develop_wt.exists() else "HEAD~10"
            sections.append(
                f"- **{repo_name}**: `{repo_path}`\n"
                f"  - Last commit: `{last_sha}`\n"
                f"  - Diff command: `git diff {diff_base}...{last_sha} --stat --patch`"
            )

    return sections, working_dir


def _build_design_mcp_directive(bud: BUDDocument, *, purpose: str) -> str:
    """Tell the agent to fetch BUD wireframes via the ``get_bud_designs`` MCP.

    Returns an empty string when the BUD has no design rows attached.
    ``purpose`` is a short verb phrase (e.g. ``"planning"``, ``"reviewing"``,
    ``"writing tests"``) used to make the instruction context-specific.

    The directive is written for the multi-repo case from the start —
    a BUD can carry one wireframe per impacted repo, so the agent
    must iterate the returned ``designs[]`` array and produce a
    section per repo rather than assuming a single wireframe.
    """
    if not bud.designs:
        return ""
    return (
        "\n## BUD Wireframes\n\n"
        f'Call `get_bud_designs` with `bud_id: "{bud.id}"` before {purpose}. '
        "The response is `designs[]` with one entry per impacted repo — "
        "iterate over every entry and match each row's `repo_name` to the "
        "repos listed in the Available Repositories section, then produce "
        "a per-repo subsection in your output covering that wireframe.\n\n"
        'Only `status: "ready"` rows are returned; the response\'s '
        "`skipped_count` field tells you how many designs are still being "
        "prepared or have failed — if it is non-zero, flag this in your "
        "output and DO NOT invent wireframe details for those repos.\n\n"
        "Do NOT inline the wireframe HTML into other outputs — refer to "
        "the design only enough to confirm the implementation matches.\n"
    )


def _build_repo_context(repo_pairs: list[tuple[str, str]]) -> str:
    """Build repo context with code-intelligence MCP instructions."""
    if not repo_pairs:
        return ""
    repo_list = "\n".join(f"- **{name}**: `{path}`" for path, name in repo_pairs)
    return (
        f"\n## Available Repositories\n\n{repo_list}\n\n"
        "## IMPORTANT: Code Exploration Rules\n\n"
        "Use bodhi code-intel MCP tools to explore the codebase. "
        "Do NOT use bash find/grep/ls.\n\n"
        "Available bodhi code-intel MCP tools:\n"
        '- `code_query({query: "concept", repo_id})` — find code by concept\n'
        '- `code_context({symbol: "name", repo_id})` — 360° view of a symbol\n'
        '- `code_impact({target: "symbol", direction: "upstream", repo_id})` — blast radius\n'
        "- `code_community({cluster_id, repo_id})` — list files/symbols in a domain cluster\n"
        "- `code_god_nodes({repo_id})` — high-degree hubs / refactoring candidates\n"
        "- `code_stats({repo_id})` — overall graph stats\n\n"
        "Start with `code_stats` for an overview, then `code_query` for the area "
        "you care about, then drill down with `code_context` and `code_impact`.\n"
    )


def _build_impacted_repos_fence(
    bud: BUDDocument,
    repo_pairs: list[tuple[str, str]],
) -> str:
    """Data-driven tail: branch convention + impacted-repos JSON fence.

    Lives in Python because both ``bud.bud_number`` and the actual list
    of impacted repo names are per-BUD. The static instructions (rules,
    sections, format, example) live in the ``tech-planner`` skill row.
    """
    repo_names = [name for _, name in repo_pairs]
    repo_names_str = ", ".join(f'"{n}"' for n in repo_names)
    return (
        f"\nBranch: `bud-{bud.bud_number:03d}/<description>`\n"
        "\n## REQUIRED: Impacted Repos JSON\n\n"
        "End your response with a fenced JSON block listing repos that need changes.\n\n"
        f"Available repos: {repo_names_str}\n\n"
        "```json\n"
        '{"impacted_repos": ["repo-name-1"], "summary": "Why each repo is impacted"}\n'
        "```\n\n"
        "Only repos with actual code changes. Parsed programmatically — do NOT omit.\n"
    )
