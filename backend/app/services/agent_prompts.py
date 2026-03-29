"""Prompt builders for BUD agent tasks.

Each builder takes a BUD, skill config, org_id, and db session,
returning (prompt_string, optional_working_dir). The prompt is
passed to Claude Code CLI for execution.
"""

import uuid as uuid_mod
from pathlib import Path
from typing import Any

from app.models.bud import BUDDocument
from app.services.skill_loader import Skill


async def build_prd_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any,
) -> tuple[str, str | None]:
    """Build PRD enrichment prompt from triage context."""
    from app.services.prompt_builder import build_prd_prompt as _build

    meta = bud.metadata_ or {}
    session_id = meta.get("triage_session_id")

    triage_context: dict = {}
    if session_id:
        from app.models.triage_session import TriageSession

        session = await db.get(TriageSession, uuid_mod.UUID(session_id))
        if session:
            triage_context = session.triage_context or {}

    prompt = await _build(
        skill_name=skill.slug,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        triage_context=triage_context,
        requirements_md=bud.requirements_md or "",
        org_id=org_id,
        db=db,
    )
    return prompt, None


async def build_tech_arch_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any,
) -> tuple[str, str | None]:
    """Build tech architecture prompt with design context and repo info."""
    from app.repositories.design_system import DesignSystemRefRepository
    from app.repositories.tracked_repository import TrackedRepoRepository

    bud_ref = f"BUD-{bud.bud_number:03d}"

    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    repo_triples = await repo_repo.get_active_id_path_name()
    repo_pairs = [(path, name) for _, path, name in repo_triples]
    working_dir = repo_triples[0][1] if repo_triples else None

    repo_id_to_name: dict[uuid_mod.UUID, str] = {}
    repo_id_to_path: dict[uuid_mod.UUID, str] = {}
    for rid, path, name in repo_triples:
        repo_id_to_name[rid] = name
        repo_id_to_path[rid] = path

    design_context = _build_design_context(bud, repo_id_to_name, repo_id_to_path)

    ds_repo = DesignSystemRefRepository(db, org_id=org_id)
    has_design_system = bool(await ds_repo.get_default())

    repo_context = _build_repo_context(repo_pairs)

    prompt = (
        f"Generate a detailed technical implementation plan for {bud_ref}: {bud.title}.\n\n"
        f"## Requirements\n\n{bud.requirements_md or ''}\n"
    )
    if design_context:
        prompt += f"\n## Design Wireframes & Notes\n{design_context}\n"
    if has_design_system:
        prompt += (
            "\n## Design System\n\n"
            "Use the `get_design_system` MCP tool to fetch design tokens. "
            "Do NOT hardcode values — reference the design system.\n"
        )
    if repo_context:
        prompt += repo_context

    has_designs = bool(design_context or has_design_system)
    prompt += _build_tech_arch_instructions(bud, repo_pairs, has_designs)

    return prompt, working_dir


async def build_code_review_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any,
) -> tuple[str, str | None]:
    """Build code review prompt with repo locations and PR-aware diffs."""
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
        confirmed_repos, last_shas, pr_branches,
    )

    if not repo_sections:
        raise ValueError("No confirmed repos with commits for code review")

    repo_list = "\n".join(repo_sections)

    bud_context = (
        f"Use `get_bud_context` MCP tool to fetch the full tech spec and requirements "
        f"for {bud_ref}. Check for deviations.\n"
    )
    if bud.tech_spec_md:
        snippet = bud.tech_spec_md[:500].rsplit("\n", 1)[0]
        bud_context += f"\nTech spec preview (use MCP for full version):\n{snippet}...\n"

    prompt = (
        f"You are performing an automated code review for {bud_ref}: {bud.title}.\n\n"
        f"## Repositories to Review\n\n{repo_list}\n\n"
        f"## BUD Context\n\n{bud_context}\n\n"
        "## How to Review\n\n"
        "1. Run `git diff` in each repo to see the actual code changes\n"
        "2. Read the modified files to understand context\n"
        "3. Use `get_bud_context` MCP tool to fetch the tech spec\n"
        "4. Check for: bugs, security issues (OWASP top 10), type safety, "
        "missing error handling, spec deviations\n\n"
        "## Output Format\n\n"
        "Produce a JSON response with this exact structure:\n"
        "```json\n"
        "{\n"
        '  "code_review_comments": [\n'
        '    {"repo": "repo_name", "file": "path/to/file.py", "line": 42,\n'
        '     "severity": "error|warning|suggestion", "comment": "...",\n'
        '     "deviates_from_spec": false}\n'
        "  ],\n"
        '  "automation_test_plan_md": "## Automated Tests\\n\\n...",\n'
        '  "manual_test_plan_md": "## Manual Tests\\n\\n..."\n'
        "}\n"
        "```\n\n"
        "Output ONLY the JSON — no markdown wrapper, no explanation."
    )

    return prompt, working_dir


async def build_testing_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any,
) -> tuple[str, str | None]:
    """Build QA testing prompt with repo locations and commit refs."""
    from app.repositories.dev_activity import DevActivityLogRepository

    bud_ref = f"BUD-{bud.bud_number:03d}"
    meta = bud.metadata_ or {}
    confirmed_repos = meta.get("confirmed_repos", [])

    activity_repo = DevActivityLogRepository(db, org_id=org_id)
    last_shas = await activity_repo.get_last_sha_per_repo(bud.id)

    repo_sections, working_dir = _build_repo_diff_sections(
        confirmed_repos, last_shas, pr_branches={},
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
        draft_context += "Expand these drafts into detailed test cases.\n\n"

    prompt = (
        f"You are generating comprehensive test cases for {bud_ref}: {bud.title}.\n\n"
        f"## Repositories\n\n{repo_list}\n\n"
        "## How to Get Context\n\n"
        "1. Use `get_bud_context` MCP tool to fetch the full tech spec\n"
        "2. Run `git diff` in each repo to see code changes\n"
        "3. Read the modified files to understand what was implemented\n"
        "4. Use gitnexus MCP tools to explore the codebase structure\n\n"
    )
    if draft_context:
        prompt += draft_context
    prompt += (
        "## Instructions\n\n"
        "Produce automation test cases (Playwright/Cucumber), "
        "manual test cases, and a test execution plan.\n"
        "Output ONLY the JSON — no markdown wrapper, no explanation.\n"
    )

    return prompt, working_dir


# ── Shared helpers ────────────────────────────────────────────────


def _build_repo_diff_sections(
    confirmed_repos: list[dict],
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
            develop_wt = Path(repo_path) / ".bodhigrove" / "develop"
            diff_base = "develop" if develop_wt.exists() else "HEAD~10"
            sections.append(
                f"- **{repo_name}**: `{repo_path}`\n"
                f"  - Last commit: `{last_sha}`\n"
                f"  - Diff command: `git diff {diff_base}...{last_sha} --stat --patch`"
            )

    return sections, working_dir


def _build_design_context(
    bud: BUDDocument,
    repo_id_to_name: dict[uuid_mod.UUID, str],
    repo_id_to_path: dict[uuid_mod.UUID, str],
) -> str:
    """Build design context string from BUD wireframes and notes."""
    parts: list[str] = []
    if not bud.designs:
        return ""
    for d in bud.designs:
        repo_name = repo_id_to_name.get(d.repo_id, "general") if d.repo_id else "general"
        repo_path = repo_id_to_path.get(d.repo_id) if d.repo_id else None

        if d.design_path or d.notes:
            parts.append(f"\n### Design: {repo_name}")
            if d.design_path and repo_path:
                full_path = f"{repo_path}/{d.design_path}"
                parts.append(
                    f"**Wireframe:** `{full_path}`\n"
                    "Read this HTML wireframe to understand the UI layout.\n"
                )
            if d.notes:
                parts.append(
                    f"**Design Notes (OVERRIDE):**\n{d.notes}\n\n"
                    "These notes take priority over the wireframe HTML.\n"
                )
    return "\n".join(parts)


def _build_repo_context(repo_pairs: list[tuple[str, str]]) -> str:
    """Build repo context with gitnexus instructions."""
    if not repo_pairs:
        return ""
    repo_list = "\n".join(f"- **{name}**: `{path}`" for path, name in repo_pairs)
    return (
        f"\n## Available Repositories\n\n{repo_list}\n\n"
        "## IMPORTANT: Code Exploration Rules\n\n"
        "Use gitnexus MCP tools to explore the codebase. "
        "Do NOT use bash find/grep/ls.\n\n"
        "Available gitnexus MCP tools:\n"
        '- `gitnexus_query({query: "concept"})` — find code by concept\n'
        '- `gitnexus_context({name: "symbolName"})` — 360° view of a symbol\n'
        '- `gitnexus_impact({target: "symbol", direction: "upstream"})` — blast radius\n'
        "- Read `gitnexus://repo/*/processes` — list execution flows\n"
        "- Read `gitnexus://repo/*/clusters` — list functional areas\n"
        "- Read `gitnexus://repo/*/context` — codebase overview\n\n"
        "Start by reading `gitnexus://repo/*/context`.\n"
    )


def _build_tech_arch_instructions(
    bud: BUDDocument,
    repo_pairs: list[tuple[str, str]],
    has_designs: bool,
) -> str:
    """Build the instructions section for tech arch prompt."""
    instructions = "\n## Instructions\n\n"
    if has_designs:
        instructions += (
            "Create a tech spec that **aligns with the designs**.\n\n"
            "The tech spec MUST:\n"
            "- Read wireframe HTML files for UI layout\n"
            "- Reference UI components and screens from wireframes\n"
            "- Use design system tokens\n"
            "- Map wireframe screens to files/routes\n"
            "- Include data model changes for the UI\n\n"
        )
    else:
        instructions += "Create a comprehensive tech spec.\n\n"

    instructions += (
        "Cover:\n"
        "- Architecture approach and key decisions\n"
        "- Files to create or modify (full paths)\n"
        "- Data model changes, API endpoints, frontend components\n"
        "- Dependencies, integration points, risks\n\n"
    )
    if repo_pairs:
        steps = []
        if has_designs:
            steps.append("Read the wireframe files listed in the Design section.")
        steps.append("Read `gitnexus://repo/*/context` for a codebase overview.")
        steps.append("Use `gitnexus_query` to find related code.")
        steps.append("Use `gitnexus_context` on key symbols.")
        steps.append("Output the plan as clean markdown.")
        for i, step in enumerate(steps, 1):
            instructions += f"{i}. {step}\n"
        instructions += "\nREMEMBER: Use gitnexus MCP tools, NOT bash find/grep/ls.\n"
    else:
        instructions += "Output the plan as clean markdown."

    instructions += (
        "\n## Include in your output\n\n"
        "At the end, add a **Development Workflow** section:\n\n"
        f"- Branch: `bud-{bud.bud_number:03d}/<description>`\n"
    )
    return instructions
