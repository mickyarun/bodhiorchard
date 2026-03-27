"""Unified BUD agent task handler.

Single handler for all BUD-level agent tasks (PRD, tech arch, code review).
Dispatches to per-type prompt builders and result handlers via an extensible
registry. Adding a new agent type = add a builder + handler entry.
"""

import uuid as uuid_mod
from typing import Any, Protocol

import structlog

from app.models.bud import BUDDocument
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.schemas.jobs import BUDAgentTaskPayload, JobState
from app.services.job_queue import update_job
from app.services.job_utils import make_progress_callback, record_agent_timeline
from app.services.skill_loader import Skill

logger = structlog.get_logger(__name__)


# ── Protocol for per-type prompt builders ─────────────────────────


class PromptBuilder(Protocol):
    """Protocol for building an agent prompt from BUD state."""

    async def __call__(
        self, bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any
    ) -> tuple[str, str | None]:
        """Build the prompt and optional working directory.

        Args:
            bud: The BUD document.
            skill: The loaded skill config.
            org_id: Organization UUID.
            db: Async database session.

        Returns:
            Tuple of (prompt_string, optional_working_dir).
        """
        ...


class ResultHandler(Protocol):
    """Protocol for handling agent output after Claude completes."""

    async def __call__(
        self,
        bud_id: uuid_mod.UUID,
        org_id: uuid_mod.UUID,
        output: str,
        task: BUDAgentTask,
        db: Any,
    ) -> dict | None:
        """Process agent output and persist results.

        Args:
            bud_id: The BUD UUID.
            org_id: The org UUID.
            output: Raw Claude output text.
            task: The agent task row.
            db: Async database session.

        Returns:
            Optional result_summary dict for the task row.
        """
        ...


# ── Per-type prompt builders ──────────────────────────────────────


async def _build_prd_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any
) -> tuple[str, str | None]:
    """Build PRD enrichment prompt from triage context."""
    from app.services.prompt_builder import build_prd_prompt

    meta = bud.metadata_ or {}
    session_id = meta.get("triage_session_id")

    # Load triage context if available
    triage_context: dict = {}
    if session_id:
        from app.models.triage_session import TriageSession

        session = await db.get(TriageSession, uuid_mod.UUID(session_id))
        if session:
            triage_context = session.triage_context or {}

    prompt = await build_prd_prompt(
        skill_name=skill.slug,
        bud_number=bud.bud_number,
        bud_title=bud.title,
        triage_context=triage_context,
        requirements_md=bud.requirements_md or "",
        org_id=org_id,
        db=db,
    )
    return prompt, None


async def _build_tech_arch_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any
) -> tuple[str, str | None]:
    """Build tech architecture prompt with design context and repo info."""
    from app.repositories.design_system import DesignSystemRefRepository
    from app.repositories.tracked_repository import TrackedRepoRepository

    bud_ref = f"BUD-{bud.bud_number:03d}"

    # Fetch repos in a single query (id, path, name)
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    repo_triples = await repo_repo.get_active_id_path_name()
    repo_pairs = [(path, name) for _, path, name in repo_triples]
    working_dir = repo_triples[0][1] if repo_triples else None

    # Build lookup maps from the single query
    repo_id_to_name: dict[uuid_mod.UUID, str] = {}
    repo_id_to_path: dict[uuid_mod.UUID, str] = {}
    for rid, path, name in repo_triples:
        repo_id_to_name[rid] = name
        repo_id_to_path[rid] = path

    # Gather design context: wireframe paths + notes (override)
    design_context = ""
    if bud.designs:
        for d in bud.designs:
            repo_name = repo_id_to_name.get(d.repo_id, "general") if d.repo_id else "general"
            repo_path = repo_id_to_path.get(d.repo_id) if d.repo_id else None

            if d.design_path or d.notes:
                design_context += f"\n### Design: {repo_name}\n"
                if d.design_path and repo_path:
                    full_path = f"{repo_path}/{d.design_path}"
                    design_context += (
                        f"**Wireframe:** `{full_path}`\n"
                        "Read this HTML wireframe to understand the UI layout and components.\n\n"
                    )
                if d.notes:
                    design_context += (
                        f"**Design Notes (OVERRIDE):**\n{d.notes}\n\n"
                        "These notes take priority over the wireframe HTML. "
                        "If notes contain Figma links, reference designs, "
                        "or specific instructions, "
                        "follow them and override the generated wireframe where they conflict.\n\n"
                    )

    # Check if design systems exist (for conditional instructions)
    ds_repo = DesignSystemRefRepository(db, org_id=org_id)
    has_design_system = bool(await ds_repo.get_default())

    # Build repo context
    repo_context = ""
    if repo_pairs:
        repo_list = "\n".join(f"- **{name}**: `{path}`" for path, name in repo_pairs)
        repo_context = (
            f"\n## Available Repositories\n\n{repo_list}\n\n"
            "## IMPORTANT: Code Exploration Rules\n\n"
            "You MUST use the gitnexus MCP tools to explore the codebase. "
            "Do NOT use bash commands like `find`, `grep`, `ls`, or `cat` "
            "for code exploration — use gitnexus instead.\n\n"
            "Available gitnexus MCP tools:\n"
            '- `gitnexus_query({query: "concept"})` — find code by concept\n'
            '- `gitnexus_context({name: "symbolName"})` — 360° view of a symbol\n'
            '- `gitnexus_impact({target: "symbol", direction: "upstream"})` — blast radius\n'
            "- Read `gitnexus://repo/*/processes` — list all execution flows\n"
            "- Read `gitnexus://repo/*/clusters` — list all functional areas\n"
            "- Read `gitnexus://repo/*/context` — codebase overview\n\n"
            "Start by reading `gitnexus://repo/*/context` to understand the codebase.\n"
        )

    # Assemble prompt
    prompt = (
        f"Generate a detailed technical implementation plan for {bud_ref}: {bud.title}.\n\n"
        f"## Requirements\n\n{bud.requirements_md or ''}\n"
    )
    if design_context:
        prompt += f"\n## Design Wireframes & Notes\n{design_context}\n"
    if has_design_system:
        prompt += (
            "\n## Design System\n\n"
            "Use the `get_design_system` MCP tool to fetch design tokens "
            "(colors, typography, spacing, component defaults) when needed. "
            "Do NOT hardcode values — reference the design system.\n"
        )
    if repo_context:
        prompt += repo_context

    has_designs = bool(design_context or has_design_system)

    instructions = "\n## Instructions\n\n"
    if has_designs:
        instructions += (
            "Create a comprehensive tech spec that **aligns with the designs**.\n\n"
            "The tech spec MUST:\n"
            "- Read the wireframe HTML files to understand the UI layout\n"
            "- Reference specific UI components and screens from the wireframes\n"
            "- Use the design system tokens (colors, typography, spacing)\n"
            "- Map each wireframe screen to specific files/routes\n"
            "- Include data model changes needed to support the UI\n\n"
        )
    else:
        instructions += "Create a comprehensive tech spec.\n\n"

    instructions += (
        "Cover:\n"
        "- Architecture approach and key design decisions\n"
        "- Files to create or modify (with full paths)\n"
        "- Data model changes\n"
        "- API endpoints\n"
        "- Frontend components\n"
        "- Dependencies and integration points\n"
        "- Risk areas and mitigation strategies\n\n"
    )
    if repo_pairs:
        steps = []
        if has_designs:
            steps.append("Read the wireframe files listed in the Design section.")
        steps.append("Read `gitnexus://repo/*/context` for a codebase overview.")
        steps.append("Use `gitnexus_query` to find code related to the requirements.")
        steps.append("Use `gitnexus_context` on key symbols to understand deps.")
        steps.append("Output the plan as clean markdown.")
        for i, step in enumerate(steps, 1):
            instructions += f"{i}. {step}\n"
        instructions += (
            "\nREMEMBER: Use gitnexus MCP tools for code exploration, "
            "NOT bash find/grep/ls.\n"
        )
    else:
        instructions += "Output the plan as clean markdown."

    # Instruct agent to include branch naming in its output
    instructions += (
        "\n## Include in your output\n\n"
        "At the end of the tech spec, add a **Development Workflow** "
        "section with the branch naming convention:\n\n"
        f"- Branch: `bud-{bud.bud_number:03d}/<description>`\n"
    )
    prompt += instructions

    return prompt, working_dir


async def _build_code_review_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any
) -> tuple[str, str | None]:
    """Build a lean code review prompt with repo locations and commit SHAs.

    Instead of embedding full diffs and tech specs inline, provides the agent
    with repo paths, branch info, and commit SHAs so it can use tools (Read,
    Bash git diff, gitnexus MCP) to explore code itself.
    """
    from pathlib import Path

    from app.repositories.dev_activity import DevActivityLogRepository

    bud_ref = f"BUD-{bud.bud_number:03d}"
    meta = bud.metadata_ or {}
    confirmed_repos = meta.get("confirmed_repos", [])

    activity_repo = DevActivityLogRepository(db, org_id=org_id)
    last_shas = await activity_repo.get_last_sha_per_repo(bud.id)

    # Build repo context: paths + last commit SHAs
    repo_sections: list[str] = []
    working_dir: str | None = None

    for repo_info in confirmed_repos:
        repo_path = repo_info.get("repo_path", "")
        repo_name = repo_info.get("repo_name", Path(repo_path).name)
        if not repo_path:
            continue
        if working_dir is None:
            working_dir = repo_path

        last_sha = last_shas.get(repo_path, "HEAD")
        develop_wt = Path(repo_path) / ".bodhigrove" / "develop"
        diff_base = "develop" if develop_wt.exists() else "HEAD~10"

        repo_sections.append(
            f"- **{repo_name}**: `{repo_path}`\n"
            f"  - Last commit: `{last_sha}`\n"
            f"  - Diff command: `git diff {diff_base}...{last_sha} --stat --patch`"
        )

    if not repo_sections:
        raise ValueError("No confirmed repos with commits for code review")

    repo_list = "\n".join(repo_sections)

    # Build the BUD context reference (use MCP tool instead of inline)
    bud_context = (
        f"Use `get_bud_context` MCP tool to fetch the full tech spec and requirements "
        f"for {bud_ref}. The tech spec contains the implementation plan this code "
        f"should follow — check for deviations.\n"
    )
    # If MCP is unavailable, provide a brief summary as fallback
    if bud.tech_spec_md:
        # Just the first 500 chars as a hint, not the full spec
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
        "    {\n"
        '      "repo": "repo_name",\n'
        '      "file": "path/to/file.py",\n'
        '      "line": 42,\n'
        '      "severity": "error|warning|suggestion",\n'
        '      "comment": "Description of the issue",\n'
        '      "deviates_from_spec": false\n'
        "    }\n"
        "  ],\n"
        '  "automation_test_plan_md": "## Automated Tests\\n\\n...",\n'
        '  "manual_test_plan_md": "## Manual Tests\\n\\n..."\n'
        "}\n"
        "```\n\n"
        "Output ONLY the JSON — no markdown wrapper, no explanation."
    )

    return prompt, working_dir


# ── Per-type result handlers ──────────────────────────────────────


async def _handle_prd_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """PRD result: Claude wrote to BUD via MCP write_bud tool — just log success."""
    return {"section": "requirements_md", "output_length": len(output)}


async def _handle_tech_arch_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """Tech arch result: save output to tech_spec_md and populate impacted_repos."""
    from app.repositories.bud import BUDRepository
    from app.repositories.tracked_repository import TrackedRepoRepository

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud:
        bud.tech_spec_md = output

        # Populate impacted_repos from designs + active repos
        repo_repo = TrackedRepoRepository(db, org_id=org_id)
        repo_triples = await repo_repo.get_active_id_path_name()

        impacted: list[dict[str, str]] = []
        design_repo_ids = {d.repo_id for d in (bud.designs or []) if d.repo_id}

        for rid, _path, name in repo_triples:
            if rid in design_repo_ids:
                impacted.append({"repo_id": str(rid), "repo_name": name})

        # If no designs, include all active repos (tech spec covers everything)
        if not impacted:
            impacted = [
                {"repo_id": str(rid), "repo_name": name}
                for rid, _path, name in repo_triples
            ]

        bud.impacted_repos = impacted
        await db.flush()

    # Send approval notification
    if bud and bud.assignee_id:
        from app.services.notification_service import send_lifecycle_notification

        bud_ref = f"BUD-{bud.bud_number:03d}"
        send_lifecycle_notification(
            org_id=str(org_id),
            user_id=str(bud.assignee_id),
            notification_type="approval_requested",
            title=f"Tech plan ready for review: {bud_ref}",
            message=f'The tech architecture for "{bud.title}" needs your approval.',
            bud_id=str(bud_id),
        )

    return {"section": "tech_spec_md", "output_length": len(output)}


async def _handle_code_review_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """Code review result: parse JSON, store comments, auto-transition if clean re-review."""
    from app.repositories.bud import BUDRepository
    from app.services.job_agents import _parse_code_review_output

    review_data = _parse_code_review_output(output)

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    qa_push_requested = False
    comment_count = 0

    if bud:
        meta = dict(bud.metadata_ or {})
        qa_push_requested = meta.pop("qa_push_requested", False)
        new_comments = review_data.get("code_review_comments", [])
        meta["code_review_comments"] = new_comments
        # Clear old resolutions since comments changed
        if qa_push_requested:
            meta.pop("code_review_resolutions", None)
        auto_plan = review_data.get("automation_test_plan_md", "")
        manual_plan = review_data.get("manual_test_plan_md", "")
        if auto_plan or manual_plan:
            meta["automation_test_plan_md"] = auto_plan
            meta["manual_test_plan_md"] = manual_plan
        bud.metadata_ = meta
        comment_count = len(new_comments)

        # Auto-transition to testing if this was a re-review and no new issues
        if qa_push_requested and comment_count == 0:
            from app.models.bud import BUDStatus
            from app.services.bud_assignment import auto_assign_for_phase
            from app.services.bud_timeline import record_event

            old_status = bud.status
            bud.status = BUDStatus.TESTING
            await record_event(
                db, org_id, bud_id, "status_change",
                detail={"from": old_status, "to": "testing", "auto": True},
            )
            await auto_assign_for_phase(db, org_id, bud, BUDStatus.TESTING)

            # Trigger QA agent task
            from app.services.bud_agent_trigger import create_agent_task_for_stage

            await create_agent_task_for_stage(
                bud, "testing", org_id, db, force=True,
            )

        await db.flush()

    return {
        "section": "test_plan_md",
        "comment_count": comment_count,
        "auto_transitioned": qa_push_requested and comment_count == 0,
    }


# ── Testing (QA) prompt builder + result handler ─────────────────


async def _build_testing_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any
) -> tuple[str, str | None]:
    """Build a lean QA testing prompt with repo locations and commit refs.

    Provides the agent with repo paths and commit SHAs so it can use tools
    to explore code and diffs itself, rather than embedding everything inline.
    """
    from pathlib import Path

    from app.repositories.dev_activity import DevActivityLogRepository

    bud_ref = f"BUD-{bud.bud_number:03d}"
    meta = bud.metadata_ or {}
    confirmed_repos = meta.get("confirmed_repos", [])

    activity_repo = DevActivityLogRepository(db, org_id=org_id)
    last_shas = await activity_repo.get_last_sha_per_repo(bud.id)

    # Build repo context: paths + last commit SHAs
    repo_sections: list[str] = []
    working_dir: str | None = None

    for repo_info in confirmed_repos:
        repo_path = repo_info.get("repo_path", "")
        repo_name = repo_info.get("repo_name", Path(repo_path).name)
        if not repo_path:
            continue
        if working_dir is None:
            working_dir = repo_path

        last_sha = last_shas.get(repo_path, "HEAD")
        develop_wt = Path(repo_path) / ".bodhigrove" / "develop"
        diff_base = "develop" if develop_wt.exists() else "HEAD~10"

        repo_sections.append(
            f"- **{repo_name}**: `{repo_path}`\n"
            f"  - Last commit: `{last_sha}`\n"
            f"  - Diff command: `git diff {diff_base}...{last_sha} --stat --patch`"
        )

    repo_list = "\n".join(repo_sections) if repo_sections else "(no repos confirmed)"

    # Draft test plans from code review (keep these inline — they're short)
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
            "Expand these drafts into detailed, structured test cases "
            "with concrete inputs and expected outputs.\n\n"
        )

    prompt = (
        f"You are generating comprehensive test cases for {bud_ref}: {bud.title}.\n\n"
        f"## Repositories\n\n{repo_list}\n\n"
        f"## How to Get Context\n\n"
        f"1. Use `get_bud_context` MCP tool to fetch the full tech spec and requirements\n"
        f"2. Run `git diff` in each repo to see the actual code changes\n"
        f"3. Read the modified files to understand what was implemented\n"
        f"4. Use gitnexus MCP tools to explore the codebase structure\n\n"
    )

    if draft_context:
        prompt += draft_context

    prompt += (
        "## Instructions\n\n"
        "Analyze the requirements, tech spec, and code changes to produce:\n"
        "1. **Automation test cases** — Playwright/Cucumber scenarios with Gherkin, "
        "concrete inputs, and expected outputs\n"
        "2. **Manual test cases** — step-by-step procedures for things automation "
        "can't easily cover (accessibility, usability, visual regression)\n"
        "3. **Test execution plan** — recommended order and strategy\n\n"
        "Output ONLY the JSON — no markdown wrapper, no explanation.\n"
    )

    return prompt, working_dir


def _normalize_testing_output(parsed: dict[str, Any]) -> dict[str, Any]:
    """Normalize various agent output structures into the expected format.

    The QA agent may produce different key names or nested structures.
    This function extracts test cases regardless of the format used.
    """
    # Try direct keys first (exact match)
    auto = parsed.get("automation_test_cases", [])
    manual = parsed.get("manual_test_cases", [])
    plan = parsed.get("test_execution_plan", "")

    # Fallback: "automation" key with nested sub-keys (e.g. {api: [...], web: [...]})
    if not auto and "automation" in parsed:
        auto_section = parsed["automation"]
        if isinstance(auto_section, list):
            auto = auto_section
        elif isinstance(auto_section, dict):
            # Flatten nested groups: {"api": [...], "web": [...]} → single list
            for group in auto_section.values():
                if isinstance(group, list):
                    auto.extend(group)

    # Fallback: "manual" key
    if not manual and "manual" in parsed:
        manual_section = parsed["manual"]
        if isinstance(manual_section, list):
            manual = manual_section
        elif isinstance(manual_section, dict):
            for group in manual_section.values():
                if isinstance(group, list):
                    manual.extend(group)

    # Fallback: "execution_plan" or "test_plan" key
    if not plan:
        plan = parsed.get("execution_plan", "") or parsed.get("test_plan", "")
        if isinstance(plan, dict):
            # Convert dict plan to markdown
            plan = str(plan)

    return {
        "automation_test_cases": auto if isinstance(auto, list) else [],
        "manual_test_cases": manual if isinstance(manual, list) else [],
        "test_execution_plan": plan if isinstance(plan, str) else "",
    }


async def _handle_testing_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """Testing result: parse JSON and store test cases in dedicated BUD columns."""
    from app.repositories.bud import BUDRepository
    from app.services.json_parser import parse_json_response

    default: dict[str, Any] = {
        "automation_test_cases": [],
        "manual_test_cases": [],
        "test_execution_plan": "",
    }

    parsed_data = default
    if output:
        try:
            parsed = parse_json_response(output)
            if isinstance(parsed, dict):
                parsed_data = _normalize_testing_output(parsed)
        except Exception:
            logger.warning("testing_output_parse_failed", bud_id=str(bud_id))

    # Initialize manual test case results as pending
    for case in parsed_data["manual_test_cases"]:
        if "result" not in case:
            case["result"] = "pending"
        if "evidence" not in case:
            case["evidence"] = []
        case.setdefault("tester_name", None)
        case.setdefault("tested_at", None)

    auto_count = len(parsed_data["automation_test_cases"])
    manual_count = len(parsed_data["manual_test_cases"])

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud:
        bud.qa_automation_cases = parsed_data["automation_test_cases"]
        bud.qa_manual_cases = parsed_data["manual_test_cases"]
        bud.qa_execution_plan_md = parsed_data["test_execution_plan"]

        # Also populate test_plan_md with a human-readable summary
        bud.test_plan_md = (
            f"# Test Plan for BUD-{bud.bud_number:03d}\n\n"
            f"- **{auto_count}** automation test cases\n"
            f"- **{manual_count}** manual test cases\n\n"
            f"{parsed_data['test_execution_plan']}"
        )
        await db.flush()

    # Send notification to assigned QA
    if bud and bud.assignee_id:
        from app.services.notification_service import send_lifecycle_notification

        bud_ref = f"BUD-{bud.bud_number:03d}"
        try:
            send_lifecycle_notification(
                org_id=str(org_id),
                user_id=str(bud.assignee_id),
                notification_type="testing_ready",
                title=f"Test cases ready: {bud_ref}",
                message=(
                    f'Test cases for "{bud.title}" are ready. '
                    f"{auto_count} automation + {manual_count} manual test cases."
                ),
                bud_id=str(bud_id),
            )
        except Exception:
            logger.warning("testing_notification_failed", bud_id=str(bud_id))

    return {
        "section": "qa_execution_plan_md",
        "automation_count": auto_count,
        "manual_count": manual_count,
    }


# ── Registry ──────────────────────────────────────────────────────

PROMPT_BUILDERS: dict[str, PromptBuilder] = {
    "bud": _build_prd_prompt,
    "tech_arch": _build_tech_arch_prompt,
    "code_review": _build_code_review_prompt,
    "testing": _build_testing_prompt,
}

RESULT_HANDLERS: dict[str, ResultHandler] = {
    "bud": _handle_prd_result,
    "tech_arch": _handle_tech_arch_result,
    "code_review": _handle_code_review_result,
    "testing": _handle_testing_result,
}


# ── Unified handler ───────────────────────────────────────────────


async def handle_bud_agent_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Unified handler for all BUD-level agent tasks.

    Loads the task from DB, dispatches to the appropriate prompt builder,
    runs Claude, then dispatches to the result handler.
    """
    payload = BUDAgentTaskPayload(**raw_payload)
    task_id = uuid_mod.UUID(payload.task_id)
    org_id = uuid_mod.UUID(payload.org_id)
    bud_id = uuid_mod.UUID(payload.bud_id)

    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository

    update_job(job_id, status_message="Loading task...", progress_pct=5)

    async with AsyncSessionLocal() as db:
        try:
            task = await db.get(BUDAgentTask, task_id)
            if not task:
                update_job(job_id, state=JobState.FAILED, error="Agent task not found")
                return

            # Defense-in-depth: verify task belongs to the expected org
            if task.org_id != org_id:
                update_job(job_id, state=JobState.FAILED, error="Org mismatch")
                return

            bud_repo = BUDRepository(db, org_id=org_id)
            bud = await bud_repo.get_by_id(bud_id)
            if not bud:
                task.status = AgentTaskStatus.FAILED
                task.error_message = "BUD not found"
                await db.commit()
                update_job(job_id, state=JobState.FAILED, error="BUD not found")
                return

            # Get skill from joined relationship
            skill_row = task.skill
            if not skill_row:
                task.status = AgentTaskStatus.FAILED
                task.error_message = "Skill not found"
                await db.commit()
                update_job(job_id, state=JobState.FAILED, error="Skill not found")
                return

            # Capture scalar values for use after session closes
            _skill_slug = skill_row.skill_slug
            _task_type = task.task_type

            skill = Skill(
                name=skill_row.name,
                slug=skill_row.skill_slug,
                description=skill_row.description,
                tools=skill_row.tools,
                mcp_tools=skill_row.mcp_tools,
                prompt=skill_row.prompt,
                max_turns=skill_row.max_turns or 0,
                model=skill_row.model or "",
                effort=skill_row.effort or "",
            )

            # Dispatch to prompt builder
            builder = PROMPT_BUILDERS.get(task.task_type)
            if not builder:
                task.status = AgentTaskStatus.FAILED
                task.error_message = f"No prompt builder for task type: {task.task_type}"
                await db.commit()
                update_job(job_id, state=JobState.FAILED, error=task.error_message)
                return

            update_job(job_id, status_message="Building prompt...", progress_pct=10)
            prompt, working_dir = await builder(bud, skill, org_id, db)

            # Run Claude
            update_job(job_id, status_message="Running agent...", progress_pct=20)

            from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code
            from app.services.job_utils import build_mcp_config

            mcp = build_mcp_config(
                org_id=str(org_id),
                tool_names=skill.mcp_tools if skill.mcp_tools else None,
            )

            config = ClaudeRunnerConfig(
                max_turns=max(skill.max_turns, 0),
                timeout_seconds=600,
                mcp=mcp,
                model=skill.model or None,
                effort=skill.effort or None,
            )

            # Code review needs JSON output
            if task.task_type == "code_review":
                config.output_format = "json"

            result = await run_claude_code(
                prompt=prompt,
                working_dir=working_dir,
                config=config,
                progress_callback=make_progress_callback(job_id),
            )

            if not result.success:
                error_msg = result.error or "Agent execution failed"
                task.status = AgentTaskStatus.FAILED
                task.error_message = error_msg[:500]
                await db.commit()
                update_job(job_id, state=JobState.FAILED, error=error_msg)
                return

            # Dispatch to result handler
            update_job(job_id, status_message="Saving results...", progress_pct=90)

            handler = RESULT_HANDLERS.get(task.task_type)
            result_summary = None
            if handler:
                result_summary = await handler(bud_id, org_id, result.output or "", task, db)

            # Mark task completed
            task.status = AgentTaskStatus.COMPLETED
            task.result_summary = result_summary
            task.error_message = None
            await db.commit()

        except Exception as exc:
            await db.rollback()
            # Mark task failed
            async with AsyncSessionLocal() as err_db:
                err_task = await err_db.get(BUDAgentTask, task_id)
                if err_task:
                    err_task.status = AgentTaskStatus.FAILED
                    err_task.error_message = str(exc)[:500]
                    await err_db.commit()
            update_job(job_id, state=JobState.FAILED, error=str(exc)[:200])
            logger.exception("bud_agent_job_failed", task_id=str(task_id))
            return

    # Record timeline event (using captured scalars — safe after session close)
    await record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name=_skill_slug,
        section=_task_type,
        job_id=job_id,
    )

    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message="Done",
        progress_pct=100,
    )
