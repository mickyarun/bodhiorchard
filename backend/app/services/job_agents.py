"""Agent job handlers for triage, PRD, tech architecture, and code review.

These handlers run long-lived AI agent tasks that interact with the codebase,
Slack, and other services. Each handler follows the same pattern:
validate payload → build prompt → run Claude → persist results.
"""

import asyncio
import uuid as uuid_mod
from pathlib import Path
from typing import Any

import structlog

from app.schemas.jobs import (
    CodeReviewJobPayload,
    JobState,
    PRDAgentJobPayload,
    TechArchJobPayload,
    TriageJobPayload,
)
from app.services.job_queue import update_job
from app.services.job_utils import (
    get_thread_key,
    make_progress_callback,
    record_agent_timeline,
    thread_locks,
)
from app.services.skill_loader import load_skill

logger = structlog.get_logger(__name__)


# ── Triage handler ─────────────────────────────────────────────────


async def handle_triage_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Process a Slack triage event (start, continue, or approve/reject)."""
    payload = TriageJobPayload(**raw_payload)

    update_job(job_id, status_message=f"Processing {payload.action}...", progress_pct=10)

    thread_key = get_thread_key(payload.event_data)
    lock = thread_locks.setdefault(thread_key, asyncio.Lock())

    async with lock:
        from app.core.encryption import decrypt_secret
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            try:
                from app.api.v1.slack import _resolve_org_by_team_id

                org = await _resolve_org_by_team_id(db, payload.team_id)
                if org is None:
                    update_job(
                        job_id,
                        state=JobState.FAILED,
                        error=f"Organization not found for team {payload.team_id}",
                    )
                    return

                bot_token = decrypt_secret(org.slack_bot_token or "")
                if not bot_token:
                    update_job(job_id, state=JobState.FAILED, error="No bot token configured")
                    return

                from app.services.slack_intake import (
                    continue_triage,
                    handle_pm_approval,
                    start_triage,
                )

                event_data = payload.event_data

                if payload.action == "start_triage":
                    from app.schemas.slack import SlackReactionEvent

                    event = SlackReactionEvent.model_validate(event_data)
                    await start_triage(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.item.channel,
                        message_ts=event.item.ts,
                        requester_slack_id=event.user,
                    )
                elif payload.action == "continue_triage":
                    from app.schemas.slack import SlackMessageEvent

                    event = SlackMessageEvent.model_validate(event_data)
                    await continue_triage(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.channel,
                        thread_ts=event.thread_ts or event.ts,
                        new_message=event.text,
                        sender_slack_id=event.user or "",
                    )
                elif payload.action == "pm_approval":
                    from app.schemas.slack import SlackReactionEvent

                    event = SlackReactionEvent.model_validate(event_data)
                    await handle_pm_approval(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.item.channel,
                        message_ts=event.item.ts,
                        approver_slack_id=event.user,
                        approved=payload.approved or False,
                    )

                await db.commit()
            except Exception:
                await db.rollback()
                raise

    update_job(job_id, state=JobState.COMPLETED, status_message="Done", progress_pct=100)


# ── PRD agent handler ──────────────────────────────────────────────


async def handle_prd_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Run the PRD agent to enrich a BUD with full specification."""
    payload = PRDAgentJobPayload(**raw_payload)

    update_job(job_id, status_message="Building PRD prompt...", progress_pct=10)

    from app.core.encryption import decrypt_secret
    from app.database import AsyncSessionLocal
    from app.models.organization import Organization
    from app.models.triage_session import TriageSession
    from app.repositories.bud import BUDRepository

    async with AsyncSessionLocal() as db:
        try:
            org = await db.get(Organization, uuid_mod.UUID(payload.org_id))

            org_id = org.id if org else uuid_mod.UUID(payload.org_id)
            bud_repo = BUDRepository(db, org_id=org_id)
            bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))

            session = await db.get(TriageSession, uuid_mod.UUID(payload.session_id))

            if not all([org, bud, session]):
                update_job(job_id, state=JobState.FAILED, error="BUD, org, or session not found")
                return

            bot_token = decrypt_secret(payload.bot_token_encrypted)
            if not bot_token:
                update_job(job_id, state=JobState.FAILED, error="Failed to decrypt bot token")
                return

            update_job(job_id, status_message="Running PM agent...", progress_pct=30)

            from app.services.slack_intake import _run_prd_agent

            await _run_prd_agent(db, org, bot_token, bud, session)

            # Clear prd_job_id from metadata so frontend stops showing the banner
            meta = dict(bud.metadata_ or {})
            meta.pop("prd_job_id", None)
            bud.metadata_ = meta

            await db.commit()
        except Exception:
            await db.rollback()
            raise

    await record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name="product-manager",
        section="requirements_md",
        job_id=job_id,
    )

    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message="PRD complete",
        progress_pct=100,
    )


# ── Tech architecture handler ──────────────────────────────────────


async def handle_tech_arch_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Generate a tech architecture plan for a BUD using the tech-planner skill."""
    payload = TechArchJobPayload(**raw_payload)
    bud_ref = f"BUD-{payload.bud_number:03d}"

    update_job(job_id, status_message="Preparing tech architecture prompt...", progress_pct=10)

    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository
    from app.repositories.tracked_repository import TrackedRepoRepository

    # Load BUD to get design context + fetch active repos for the org
    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(payload.org_id))
        bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))
        if not bud:
            update_job(job_id, state=JobState.FAILED, error="BUD not found")
            return

        # Gather design info for context
        design_context = ""
        if bud.designs:
            for d in bud.designs:
                if d.design_html:
                    repo_label = d.repo_id or "general"
                    design_context += f"\n## Design ({repo_label})\n{d.design_html[:2000]}\n"

        # Fetch all active repos for the org
        repo_repo = TrackedRepoRepository(db, org_id=uuid_mod.UUID(payload.org_id))
        repo_pairs = await repo_repo.get_active_path_name_pairs()

    # Use first repo as working_dir (gitnexus MCP auto-discovers .gitnexus/ in cwd)
    working_dir = repo_pairs[0][0] if repo_pairs else None

    # Build repo context for prompt
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
            '- `gitnexus_query({query: "concept"})` — find code by concept '
            "(replaces find/grep)\n"
            '- `gitnexus_context({name: "symbolName"})` — 360° view of a '
            "symbol (callers, callees, execution flows)\n"
            '- `gitnexus_impact({target: "symbol", direction: "upstream"})` '
            "— blast radius analysis\n"
            "- Read `gitnexus://repo/*/processes` — list all execution flows\n"
            "- Read `gitnexus://repo/*/clusters` — list all functional areas\n"
            "- Read `gitnexus://repo/*/context` — codebase overview\n\n"
            "Start by reading `gitnexus://repo/*/context` to understand the "
            "codebase, then use `gitnexus_query` to find relevant code.\n"
        )

    # Build prompt for tech-planner skill
    try:
        skill = load_skill("tech-planner")
    except FileNotFoundError:
        skill = None

    prompt = (
        f"Generate a detailed technical implementation plan for {bud_ref}: {payload.title}.\n\n"
        f"## Requirements\n\n{payload.requirements_md}\n"
    )
    if design_context:
        prompt += f"\n## Existing Design Context\n{design_context}\n"
    if repo_context:
        prompt += repo_context
    if repo_pairs:
        prompt += (
            "\n## Instructions\n\n"
            "1. First, read `gitnexus://repo/*/context` to get a codebase overview.\n"
            "2. Use `gitnexus_query` to find code related to the requirements.\n"
            "3. Use `gitnexus_context` on key symbols to understand dependencies.\n"
            "4. Then create a comprehensive tech spec covering:\n"
            "   - Architecture approach and key design decisions\n"
            "   - Files to create or modify (with full paths)\n"
            "   - Data model changes (if any)\n"
            "   - API endpoints (if any)\n"
            "   - Dependencies and integration points\n"
            "   - Risk areas and mitigation strategies\n\n"
            "REMEMBER: Use gitnexus MCP tools, NOT bash find/grep/ls.\n\n"
            "Output the plan as clean markdown."
        )
    else:
        prompt += (
            "\n## Instructions\n\n"
            "Create a comprehensive tech spec covering:\n"
            "- Architecture approach and key design decisions\n"
            "- Files to create or modify (with paths)\n"
            "- Data model changes (if any)\n"
            "- API endpoints (if any)\n"
            "- Dependencies and integration points\n"
            "- Risk areas and mitigation strategies\n\n"
            "Output the plan as clean markdown."
        )

    update_job(
        job_id,
        status_message="Generating tech architecture (this may take a few minutes)...",
        progress_pct=20,
    )

    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

    result = await run_claude_code(
        prompt=prompt,
        working_dir=working_dir,
        config=ClaudeRunnerConfig(
            max_turns=skill.max_turns if skill else 3,
            timeout_seconds=600,
            model=(skill.model or None) if skill else None,
            effort=(skill.effort or None) if skill else None,
        ),
        progress_callback=make_progress_callback(job_id),
    )

    if not result.success:
        update_job(
            job_id,
            state=JobState.FAILED,
            error=result.error or "Tech architecture generation failed",
        )
        return

    # Persist to BUD
    update_job(job_id, status_message="Saving tech spec...", progress_pct=90)

    async with AsyncSessionLocal() as db:
        try:
            bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(payload.org_id))
            bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))
            if bud:
                bud.tech_spec_md = result.output
                # Clear tech_arch_job_id from metadata so frontend stops showing banner
                meta = dict(bud.metadata_ or {})
                meta.pop("tech_arch_job_id", None)
                bud.metadata_ = meta
                await db.commit()
        except Exception:
            await db.rollback()
            raise

    # Record timeline event
    await record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "tech_arch_started",
        skill_name="tech-planner",
        section="tech_spec_md",
        job_id=job_id,
    )

    # Send approval_requested notification to BUD assignee (tech_lead)
    from app.services.notification_service import send_lifecycle_notification

    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(payload.org_id))
        bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))
        if bud and bud.assignee_id:
            send_lifecycle_notification(
                org_id=payload.org_id,
                user_id=str(bud.assignee_id),
                notification_type="approval_requested",
                title=f"Tech plan ready for review: {bud_ref}",
                message=f'The tech architecture for "{payload.title}" needs your approval.',
                bud_id=payload.bud_id,
            )

    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message="Tech architecture generated",
        progress_pct=100,
    )


# ── Code review handler ────────────────────────────────────────────


async def handle_code_review_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Run automated code review + test plan generation for a BUD.

    For each confirmed repo, diffs the develop worktree against the last
    commit SHA from dev_activity_logs, then sends all diffs + tech spec to Claude
    for review comments and test plan generation.
    """
    payload = CodeReviewJobPayload(**raw_payload)
    bud_ref = f"BUD-{payload.bud_number:03d}"

    update_job(job_id, status_message="Collecting code changes...", progress_pct=10)

    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository
    from app.repositories.dev_activity import DevActivityLogRepository
    from app.services.repo_scanner import run_git

    # Step 1: Gather diffs for each confirmed repo
    all_diffs: list[dict[str, str]] = []

    async with AsyncSessionLocal() as db:
        org_id_uuid = uuid_mod.UUID(payload.org_id)
        activity_repo = DevActivityLogRepository(db, org_id=org_id_uuid)
        last_shas = await activity_repo.get_last_sha_per_repo(uuid_mod.UUID(payload.bud_id))

    for repo_info in payload.confirmed_repos:
        repo_path = repo_info.get("repo_path", "")
        repo_name = repo_info.get("repo_name", Path(repo_path).name)
        if not repo_path:
            continue

        # Pull develop worktree to latest
        develop_wt = Path(repo_path) / ".bodhigrove" / "develop"
        if develop_wt.exists():
            await run_git(["pull"], cwd=str(develop_wt))

        # Get the last commit SHA for this repo
        last_sha = last_shas.get(repo_path)
        if not last_sha:
            logger.warning("code_review_no_commits", repo=repo_name, bud=bud_ref)
            continue

        # Get diff: develop...last_sha
        diff_base = "develop" if develop_wt.exists() else "HEAD~10"
        diff_stdout, diff_stderr, rc = await run_git(
            ["diff", f"{diff_base}...{last_sha}", "--stat", "--patch"],
            cwd=repo_path,
            timeout=120,
        )
        if rc != 0:
            # Fallback: diff against HEAD
            diff_stdout, _, _ = await run_git(
                ["diff", f"HEAD~5..{last_sha}"],
                cwd=repo_path,
                timeout=120,
            )

        if diff_stdout:
            # Truncate very large diffs
            all_diffs.append(
                {
                    "repo_name": repo_name,
                    "diff": diff_stdout[:50000],
                }
            )

    if not all_diffs:
        update_job(
            job_id,
            state=JobState.FAILED,
            error="No code changes found in confirmed repos",
        )
        return

    update_job(
        job_id,
        status_message="Running AI code review (this may take a few minutes)...",
        progress_pct=30,
    )

    # Step 2: Build prompt for Claude
    diff_sections = "\n\n".join(
        f"## Repository: {d['repo_name']}\n\n```diff\n{d['diff']}\n```" for d in all_diffs
    )

    prompt = (
        f"You are performing an automated code review for {bud_ref}: {payload.title}.\n\n"
        f"## Original Tech Spec\n\n{payload.tech_spec_md[:10000]}\n\n"
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
        "For the code review:\n"
        "- Check for bugs, security issues, and code quality problems\n"
        "- Flag any deviations from the tech spec\n"
        "- Note missing error handling or edge cases\n\n"
        "For test plans:\n"
        "- automation_test_plan_md: Unit and integration tests that should be automated\n"
        "- manual_test_plan_md: Manual QA test scenarios with steps\n\n"
        "Output ONLY the JSON — no markdown wrapper, no explanation."
    )

    # Step 3: Run Claude
    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

    try:
        skill = load_skill("code-reviewer")
    except FileNotFoundError:
        skill = None

    working_dir = payload.confirmed_repos[0].get("repo_path") if payload.confirmed_repos else None
    result = await run_claude_code(
        prompt=prompt,
        working_dir=working_dir,
        config=ClaudeRunnerConfig(
            max_turns=skill.max_turns if skill else 3,
            timeout_seconds=600,
            output_format="json",
            model=(skill.model or None) if skill else None,
            effort=(skill.effort or None) if skill else None,
        ),
        progress_callback=make_progress_callback(job_id),
    )

    if not result.success:
        update_job(
            job_id,
            state=JobState.FAILED,
            error=result.error or "Code review generation failed",
        )
        return

    # Step 4: Parse and persist results
    update_job(job_id, status_message="Saving review results...", progress_pct=85)

    review_data = _parse_code_review_output(result.output)

    async with AsyncSessionLocal() as db:
        try:
            bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(payload.org_id))
            bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))
            if bud:
                meta = dict(bud.metadata_ or {})
                meta["code_review_comments"] = review_data.get("code_review_comments", [])
                meta.pop("code_review_job_id", None)
                bud.metadata_ = meta

                # Store test plans
                auto_plan = review_data.get("automation_test_plan_md", "")
                manual_plan = review_data.get("manual_test_plan_md", "")
                if auto_plan or manual_plan:
                    meta["automation_test_plan_md"] = auto_plan
                    meta["manual_test_plan_md"] = manual_plan
                    bud.metadata_ = meta

                await db.commit()
        except Exception:
            await db.rollback()
            raise

    await record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name="code-reviewer",
        section="code_review",
        job_id=job_id,
    )

    comments_count = len(review_data.get("code_review_comments", []))
    update_job(
        job_id,
        state=JobState.COMPLETED,
        result={
            "comments_count": comments_count,
            "has_auto_tests": bool(review_data.get("automation_test_plan_md")),
            "has_manual_tests": bool(review_data.get("manual_test_plan_md")),
        },
        status_message=f"Code review complete — {comments_count} comments",
        progress_pct=100,
    )


def _parse_code_review_output(output: str) -> dict[str, Any]:
    """Parse Claude's code review JSON output.

    Falls back to empty structure if parsing fails.

    Args:
        output: Raw text output from Claude.

    Returns:
        Dict with code_review_comments, automation_test_plan_md, manual_test_plan_md.
    """
    from app.services.json_parser import extract_json

    default: dict[str, Any] = {
        "code_review_comments": [],
        "automation_test_plan_md": "",
        "manual_test_plan_md": "",
    }

    if not output:
        return default

    try:
        parsed = extract_json(output)
        if isinstance(parsed, dict):
            return {
                "code_review_comments": parsed.get("code_review_comments", []),
                "automation_test_plan_md": parsed.get("automation_test_plan_md", ""),
                "manual_test_plan_md": parsed.get("manual_test_plan_md", ""),
            }
    except Exception:
        logger.warning("code_review_parse_failed", output_preview=output[:200])

    return default
