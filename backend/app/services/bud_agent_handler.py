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
    prompt += instructions

    return prompt, working_dir


async def _build_code_review_prompt(
    bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any
) -> tuple[str, str | None]:
    """Build code review prompt with git diffs from confirmed repos."""
    from pathlib import Path

    from app.repositories.bud_commit import BUDCommitRepository
    from app.services.repo_scanner import run_git

    bud_ref = f"BUD-{bud.bud_number:03d}"
    meta = bud.metadata_ or {}
    confirmed_repos = meta.get("confirmed_repos", [])

    commit_repo = BUDCommitRepository(db, org_id=org_id)
    last_shas = await commit_repo.get_last_sha_per_repo(bud.id)

    all_diffs: list[dict[str, str]] = []
    working_dir: str | None = None

    for repo_info in confirmed_repos:
        repo_path = repo_info.get("repo_path", "")
        repo_name = repo_info.get("repo_name", Path(repo_path).name)
        if not repo_path:
            continue
        if working_dir is None:
            working_dir = repo_path

        develop_wt = Path(repo_path) / ".bodhigrove" / "develop"
        if develop_wt.exists():
            await run_git(["pull"], cwd=str(develop_wt))

        last_sha = last_shas.get(repo_path)
        if not last_sha:
            continue

        diff_base = "develop" if develop_wt.exists() else "HEAD~10"
        diff_stdout, _, rc = await run_git(
            ["diff", f"{diff_base}...{last_sha}", "--stat", "--patch"],
            cwd=repo_path,
            timeout=120,
        )
        if rc != 0:
            diff_stdout, _, _ = await run_git(
                ["diff", f"HEAD~5..{last_sha}"],
                cwd=repo_path,
                timeout=120,
            )
        if diff_stdout:
            all_diffs.append({"repo_name": repo_name, "diff": diff_stdout[:50000]})

    if not all_diffs:
        raise ValueError("No code changes found in confirmed repos")

    diff_sections = "\n\n".join(
        f"## Repository: {d['repo_name']}\n\n```diff\n{d['diff']}\n```" for d in all_diffs
    )

    prompt = (
        f"You are performing an automated code review for {bud_ref}: {bud.title}.\n\n"
        f"## Original Tech Spec\n\n{(bud.tech_spec_md or '')[:10000]}\n\n"
        f"## Code Changes\n\n{diff_sections}\n\n"
        "## Instructions\n\n"
        "Review the code changes and produce a JSON response with this exact structure:\n"
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
    """Code review result: parse JSON and store comments + test plans in metadata."""
    from app.repositories.bud import BUDRepository
    from app.services.job_agents import _parse_code_review_output

    review_data = _parse_code_review_output(output)

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud:
        meta = dict(bud.metadata_ or {})
        meta["code_review_comments"] = review_data.get("code_review_comments", [])
        auto_plan = review_data.get("automation_test_plan_md", "")
        manual_plan = review_data.get("manual_test_plan_md", "")
        if auto_plan or manual_plan:
            meta["automation_test_plan_md"] = auto_plan
            meta["manual_test_plan_md"] = manual_plan
        bud.metadata_ = meta
        await db.flush()

    comment_count = len(review_data.get("code_review_comments", []))
    return {"section": "test_plan_md", "comment_count": comment_count}


# ── Registry ──────────────────────────────────────────────────────

PROMPT_BUILDERS: dict[str, PromptBuilder] = {
    "bud": _build_prd_prompt,
    "tech_arch": _build_tech_arch_prompt,
    "code_review": _build_code_review_prompt,
}

RESULT_HANDLERS: dict[str, ResultHandler] = {
    "bud": _handle_prd_result,
    "tech_arch": _handle_tech_arch_result,
    "code_review": _handle_code_review_result,
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
