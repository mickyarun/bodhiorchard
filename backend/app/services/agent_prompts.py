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
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid_mod.UUID,
    db: Any,
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
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid_mod.UUID,
    db: Any,
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
        f"Generate a concise tech spec for {bud_ref}: {bud.title}.\n\n"
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
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid_mod.UUID,
    db: Any,
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
        confirmed_repos,
        last_shas,
        pr_branches,
    )

    if not repo_sections:
        raise ValueError("No confirmed repos with commits for code review")

    repo_list = "\n".join(repo_sections)

    repo_path_map = {r.get("repo_id", ""): r.get("repo_path", "") for r in confirmed_repos}
    design_refs = _build_design_refs(bud, repo_path_map)

    prompt = (
        f"Code review for {bud_ref}: {bud.title}.\n\n"
        f"## Repos\n\n{repo_list}\n\n"
        f"{design_refs}"
        "## Scope\n\n"
        "**Review only what this diff changes. Do NOT flag pre-existing "
        "code that is unchanged.**\n\n"
        "- Only comment on lines added or modified in the diff.\n"
        "- You may read unchanged code to UNDERSTAND context, but do not "
        "  flag issues you find in unchanged lines.\n"
        "- Exception: if `gitnexus_impact` reveals d=1 callers/dependents "
        "  that the diff failed to update, you MUST flag those even though "
        "  the caller files are unchanged — the diff is incomplete.\n"
        "- Exception: if the diff adds a new call to a pre-existing buggy "
        "  function, flag the call site (not the function) only if the bug "
        "  materially affects the new usage.\n"
        "- Do NOT re-review the entire file. Do NOT propose refactors of "
        "  untouched code. Do NOT critique style of lines the author "
        "  didn't write.\n\n"
        "## Steps\n\n"
        "1. `get_bud_context` → fetch tech spec + PRD ACs\n"
        "2. `git diff` in each repo — this is your scope of review\n"
        "3. Read modified files ONLY as much as needed to understand the diff\n"
        "4. `gitnexus_impact` on key symbols — flag d=1 dependents not updated\n"
        "5. Verify each PRD AC has implementation in the diff\n\n"
        "## Quality Checklist (apply to changed lines only)\n\n"
        "| Check | Rule |\n"
        "|-------|------|\n"
        "| Bugs | Logic errors, null refs, race conditions |\n"
        "| Security | OWASP top 10, org_id scoping, input validation |\n"
        "| Modularity | Functions <50 lines, files <300 (BE) / <250 (FE) |\n"
        "| Reuse | Existing patterns used, no duplicated code |\n"
        "| No hacks | No hardcoded values, TODO/FIXME, bypassed checks |\n"
        "| Standards | Type hints, docstrings on public funcs, lint clean |\n"
        "| Spec match | Changes match tech arch + PRD acceptance criteria |\n"
        "| Impact | gitnexus blast radius — d=1 dependents updated |\n\n"
        "## Output (JSON only, no wrapper)\n\n"
        "```json\n"
        "{\n"
        '  "code_review_comments": [\n'
        '    {"repo": "name", "file": "path", "line": 42,\n'
        '     "severity": "error|warning|suggestion",\n'
        '     "comment": "...", "deviates_from_spec": false}\n'
        "  ],\n"
        '  "automation_test_plan_md": "...",\n'
        '  "manual_test_plan_md": "..."\n'
        "}\n"
        "```\n"
    )

    return prompt, working_dir


async def build_testing_prompt(
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid_mod.UUID,
    db: Any,
) -> tuple[str, str | None]:
    """Build QA testing prompt with repo locations and commit refs."""
    from app.repositories.dev_activity import DevActivityLogRepository

    bud_ref = f"BUD-{bud.bud_number:03d}"
    meta = bud.metadata_ or {}
    confirmed_repos = meta.get("confirmed_repos", [])

    activity_repo = DevActivityLogRepository(db, org_id=org_id)
    last_shas = await activity_repo.get_last_sha_per_repo(bud.id)

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

    repo_path_map = {r.get("repo_id", ""): r.get("repo_path", "") for r in confirmed_repos}
    design_refs = _build_design_refs(bud, repo_path_map)

    prompt = (
        f"You are generating structured test cases for {bud_ref}: {bud.title}.\n\n"
        f"## Repositories\n\n{repo_list}\n\n"
        f"{design_refs}"
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
        "Target 15-25 test cases total. Cover: functional, negative, boundary, "
        "stress, non-functional (a11y, perf), and impact (regression).\n"
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


def _build_design_refs(
    bud: BUDDocument,
    repo_paths: dict[str, str] | None = None,
) -> str:
    """Build a compact wireframe reference block from BUD designs.

    Used by code review and testing prompts so agents can verify
    implementation matches the approved wireframes.
    """
    if not bud.designs:
        return ""
    repo_paths = repo_paths or {}
    refs: list[str] = []
    for d in bud.designs:
        if d.design_path:
            base = repo_paths.get(str(d.repo_id), "") if d.repo_id else ""
            full = f"{base}/{d.design_path}" if base else d.design_path
            refs.append(f"- `{full}`")
        if d.notes:
            refs.append(f"  Notes: {d.notes[:200]}")
    if not refs:
        return ""
    return (
        "\n## Design References\n\n"
        "Approved wireframes (read to verify implementation matches):\n" + "\n".join(refs) + "\n"
    )


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
    instructions += (
        "**Target 3,000-6,000 characters.** Developers use Claude Code and generate "
        "implementation from this plan. No code examples, no CSS tokens, no template "
        "pseudocode, no function signatures. Every sentence must carry new information.\n\n"
    )

    if has_designs:
        instructions += (
            "Align with the designs: READ the wireframe HTML file paths listed in the "
            "**Design Wireframes & Notes** section above (use the Read tool with the "
            "full path). Map wireframe screens to files/routes. Reference design system "
            "tokens by name (not values).\n"
            "**Include the wireframe file paths in your output** under a "
            "'Design References' section so developers can find them.\n\n"
        )

    sections_list = (
        "Sections (strict format):\n"
        "- **Executive Summary**: 2-3 sentences.\n"
        "- **Architecture Approach**: Key decisions, 1 paragraph max.\n"
        "- **Files to Create or Modify**: Table (action | path | notes).\n"
        "- **API Changes**: Table (verb | path | description). Only if endpoints change.\n"
        "- **Data Model Changes**: One sentence per change. Only if schema changes.\n"
    )
    if has_designs:
        sections_list += "- **Design References**: List wireframe file paths you read.\n"
    sections_list += (
        "- **Dependencies & Risks**: Bullet points, real blockers only.\n"
        "- **Development Workflow**: Branch name + implementation order.\n"
        "- **Implementation TODO**: Numbered checklist of tasks in order. "
        "Each task = one file or logical unit. Include a code review checkpoint "
        "after each phase.\n"
        "- **Code Review Standards**: Include this exact checklist at the end — "
        "developers must verify at each phase:\n"
        "  - [ ] Modularity: each function <50 lines, each file <300 lines\n"
        "  - [ ] Security: org-scoped queries, auth on endpoints, no PII leaks, "
        "input validation at boundaries\n"
        "  - [ ] Reusability: reuse existing patterns/utilities, no duplicated code\n"
        "  - [ ] No large files: split if >300 lines backend / >250 lines frontend\n"
        "  - [ ] No hacks: no hardcoded values, no TODO/FIXME left behind, "
        "no bypassed validations\n"
        "  - [ ] Standards: type hints, docstrings on public functions, "
        "lint clean (ruff/eslint)\n\n"
    )
    instructions += sections_list

    if repo_pairs:
        steps = []
        if has_designs:
            steps.append("Read wireframe files from the Design section.")
        steps.append("Read `gitnexus://repo/*/context` for codebase overview.")
        steps.append("Use `gitnexus_query` to find related code.")
        steps.append("Use `gitnexus_context` on key symbols.")
        steps.append("Output the plan as clean markdown.")
        for i, step in enumerate(steps, 1):
            instructions += f"{i}. {step}\n"
        instructions += "\nUse gitnexus MCP tools, NOT bash find/grep/ls.\n"

    repo_names = [name for _, name in repo_pairs]
    repo_names_str = ", ".join(f'"{n}"' for n in repo_names)

    instructions += (
        f"\nBranch: `bud-{bud.bud_number:03d}/<description>`\n"
        "\n## REQUIRED: Impacted Repos JSON\n\n"
        "End your response with a fenced JSON block listing repos that need changes.\n\n"
        f"Available repos: {repo_names_str}\n\n"
        "```json\n"
        '{"impacted_repos": ["repo-name-1"], "summary": "Why each repo is impacted"}\n'
        "```\n\n"
        "Only repos with actual code changes. Parsed programmatically — do NOT omit.\n"
    )
    return instructions
