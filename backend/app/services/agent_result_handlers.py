"""Result handlers for BUD agent tasks.

Each handler processes Claude's output, persists results to the database,
and optionally triggers follow-up actions (notifications, status transitions).
"""

import uuid as uuid_mod
from typing import Any

import structlog

from app.models.bud_agent_task import BUDAgentTask

logger = structlog.get_logger(__name__)


async def handle_prd_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """PRD result: Claude wrote to BUD via MCP write_bud tool — trigger first estimation."""
    # Generate initial delivery estimates now that PRD content exists
    try:
        from app.repositories.bud import BUDRepository
        from app.services.bud_estimation import estimate_bud_dates

        bud_repo = BUDRepository(db, org_id=org_id)
        bud = await bud_repo.get_by_id(bud_id)
        if bud:
            await estimate_bud_dates(db, org_id, bud, trigger="prd_completed")
    except Exception:
        logger.warning("estimation_failed_after_prd", bud_id=str(bud_id))

    return {"section": "requirements_md", "output_length": len(output)}


async def handle_tech_arch_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """Tech arch result: save output to tech_spec_md and populate impacted_repos.

    The agent outputs markdown followed by a JSON block with impacted_repos.
    We parse that JSON to determine which repos actually need changes,
    then strip the JSON block before storing the markdown.
    """
    from app.repositories.bud import BUDRepository
    from app.repositories.tracked_repository import TrackedRepoRepository

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud:
        # Extract impacted repos from the last JSON fence, then strip it
        impacted_names, clean_output = _extract_impacted_repos_json(output)
        bud.tech_spec_md = clean_output

        repo_repo = TrackedRepoRepository(db, org_id=org_id)
        repo_triples = await repo_repo.get_active_id_path_name()
        name_to_repo = {name.lower(): (rid, name) for rid, _path, name in repo_triples}

        # Match agent-declared repo names against tracked repos
        impacted: list[dict[str, str]] = []
        for declared_name in impacted_names:
            match = name_to_repo.get(declared_name.lower())
            if match:
                rid, name = match
                impacted.append({"repo_id": str(rid), "repo_name": name})

        if not impacted:
            logger.warning(
                "tech_arch_no_impacted_repos_parsed",
                bud_id=str(bud_id),
                raw_names=impacted_names,
            )

        bud.impacted_repos = impacted
        await db.flush()

        # Re-estimate with richer context (now has tech spec + impacted repos)
        try:
            from app.services.bud_estimation import estimate_bud_dates

            await estimate_bud_dates(db, org_id, bud, trigger="tech_arch_completed")
        except Exception:
            logger.warning("estimation_failed_after_tech_arch", bud_id=str(bud_id))

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


async def handle_code_review_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """Code review result: parse JSON, store comments, auto-transition if clean."""
    from app.repositories.bud import BUDRepository

    review_data = _parse_code_review_output(output)

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    qa_push_requested = False
    comment_count = 0

    if bud:
        meta = dict(bud.metadata_ or {})
        qa_push_requested = meta.pop("qa_push_requested", False)
        new_comments = review_data.get("code_review_comments", [])

        # Re-review semantics: drop previously stored agent-sourced comments
        # before storing this run's output. Keeps human GitHub review comments
        # (source: "github") and manual frontend additions (source: "manual")
        # intact, so we never wipe human-authored feedback. The parallel
        # resolutions array is remapped to preserve the user's resolution
        # state on surviving human/manual comments.
        existing_comments = list(bud.code_review_comments or [])
        existing_resolutions = meta.get("code_review_resolutions") or []
        kept_comments: list[dict] = []
        kept_resolutions: list[dict] = []
        for idx, c in enumerate(existing_comments):
            if c.get("source") == "agent":
                continue
            kept_comments.append(c)
            if idx < len(existing_resolutions):
                kept_resolutions.append(existing_resolutions[idx])
            else:
                kept_resolutions.append({"done": None, "comment": ""})

        dropped = len(existing_comments) - len(kept_comments)
        if dropped:
            bud.code_review_comments = kept_comments
            if kept_resolutions:
                meta["code_review_resolutions"] = kept_resolutions
            else:
                meta.pop("code_review_resolutions", None)
            logger.info(
                "code_review_old_agent_comments_cleared",
                bud_id=str(bud_id),
                dropped=dropped,
                kept=len(kept_comments),
            )

        # Comments stored via GitHub webhook (issue_comment/review_comment),
        # not directly here. We only sync outbound to GitHub PR.
        if qa_push_requested:
            meta.pop("code_review_resolutions", None)
        auto_plan = review_data.get("automation_test_plan_md", "")
        manual_plan = review_data.get("manual_test_plan_md", "")
        if auto_plan or manual_plan:
            meta["automation_test_plan_md"] = auto_plan
            meta["manual_test_plan_md"] = manual_plan
        bud.metadata_ = meta
        comment_count = len(new_comments)

        if new_comments:
            from app.services.github_pr_sync import sync_review_comments_to_github

            await sync_review_comments_to_github(bud_id, org_id, new_comments, db)

        if qa_push_requested and comment_count == 0:
            # Verify ACs before auto-transitioning to testing
            ac_passed = True
            try:
                from app.services.ac_verification import verify_ac_completeness

                ac_passed, _ = await verify_ac_completeness(db, org_id, bud)
            except Exception:
                logger.warning("ac_verification_error_in_review", bud_id=str(bud_id))

            if ac_passed:
                from app.models.bud import BUDStatus
                from app.services.bud_assignment import auto_assign_for_phase
                from app.services.bud_timeline import record_event

                old_status = bud.status
                bud.status = BUDStatus.TESTING
                await record_event(
                    db,
                    org_id,
                    bud_id,
                    "status_change",
                    detail={"from": old_status, "to": "testing", "auto": True},
                )
                await auto_assign_for_phase(db, org_id, bud, BUDStatus.TESTING)

                from app.services.bud_agent_trigger import create_agent_task_for_stage

                await create_agent_task_for_stage(bud, "testing", org_id, db, force=True)
            else:
                logger.info("ac_blocked_testing_after_review", bud_id=str(bud_id))

        await db.flush()

    # Return immediately so the agent completion event fires fast.
    # Estimation runs after the handler returns (deferred in bud_agent_handler).
    return {
        "section": "test_plan_md",
        "comment_count": comment_count,
        "auto_transitioned": qa_push_requested and comment_count == 0,
        "_deferred_estimation": True,
    }


async def handle_testing_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """Testing result: parse JSON and store test cases in BUD columns."""
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
        bud.test_plan_md = (
            f"# Test Plan for BUD-{bud.bud_number:03d}\n\n"
            f"- **{auto_count}** automation test cases\n"
            f"- **{manual_count}** manual test cases\n\n"
            f"{parsed_data['test_execution_plan']}"
        )
        # Re-estimate with QA test case context
        try:
            from app.services.bud_estimation import estimate_bud_dates

            await estimate_bud_dates(db, org_id, bud, trigger="testing_completed")
        except Exception:
            logger.warning("estimation_failed_after_testing", bud_id=str(bud_id))
        await db.flush()

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


# ── Output parsing helpers ────────────────────────────────────────


def _extract_impacted_repos_json(output: str) -> tuple[list[str], str]:
    """Extract impacted repo names from the last JSON fence and return cleaned markdown.

    Returns:
        (impacted_names, clean_output) — list of repo name strings and
        the markdown with the JSON block (and its heading) stripped.
    """
    import json
    import re

    impacted_names: list[str] = []
    clean = output

    # Find the *last* ```json ... ``` fence (agent appends it at the end)
    fences = list(re.finditer(r"```json\s*\n(.*?)\n\s*```", output, re.DOTALL))
    if fences:
        last_fence = fences[-1]
        try:
            parsed = json.loads(last_fence.group(1))
            if isinstance(parsed, dict) and isinstance(parsed.get("impacted_repos"), list):
                impacted_names = parsed["impacted_repos"]
        except json.JSONDecodeError:
            logger.warning("tech_arch_impacted_json_parse_failed")

        # Strip the JSON block and its section heading from stored markdown
        strip_start = last_fence.start()
        # Also remove the heading above the fence if present
        heading_pattern = re.compile(
            r"#{1,3}\s*(?:REQUIRED:\s*)?Impacted Repos JSON\s*\n+",
            re.IGNORECASE,
        )
        before = clean[:strip_start]
        heading_match = heading_pattern.search(before)
        if heading_match and heading_match.end() >= len(before.rstrip()):
            strip_start = heading_match.start()

        clean = output[:strip_start].rstrip() + "\n"

    return impacted_names, clean


def _parse_code_review_output(output: str) -> dict[str, Any]:
    """Parse code review JSON output from Claude.

    Comments are stored via GitHub webhook (not here). This only
    extracts structured JSON if the agent returned it, for the
    comment_count used in auto-transition logic.
    """
    from app.services.json_parser import parse_json_response

    try:
        parsed = parse_json_response(output)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        logger.warning("code_review_output_parse_failed")
    return {"code_review_comments": []}


def _normalize_testing_output(parsed: dict[str, Any]) -> dict[str, Any]:
    """Normalize various agent output structures into expected format."""
    auto = parsed.get("automation_test_cases", [])
    manual = parsed.get("manual_test_cases", [])
    plan = parsed.get("test_execution_plan", "")

    if not auto and "automation" in parsed:
        auto_section = parsed["automation"]
        if isinstance(auto_section, list):
            auto = auto_section
        elif isinstance(auto_section, dict):
            for group in auto_section.values():
                if isinstance(group, list):
                    auto.extend(group)

    if not manual and "manual" in parsed:
        manual_section = parsed["manual"]
        if isinstance(manual_section, list):
            manual = manual_section
        elif isinstance(manual_section, dict):
            for group in manual_section.values():
                if isinstance(group, list):
                    manual.extend(group)

    if not plan:
        plan = parsed.get("execution_plan", "") or parsed.get("test_plan", "")

    if isinstance(plan, dict):
        plan = _dict_plan_to_markdown(plan)
    elif isinstance(plan, list):
        plan = "\n".join(f"- {item}" if isinstance(item, str) else str(item) for item in plan)
    elif not isinstance(plan, str):
        plan = ""

    return {
        "automation_test_cases": auto if isinstance(auto, list) else [],
        "manual_test_cases": manual if isinstance(manual, list) else [],
        "test_execution_plan": plan,
    }


def _dict_plan_to_markdown(plan: dict[str, Any]) -> str:
    """Convert a dict execution plan to readable markdown."""
    import json

    lines: list[str] = []

    if "strategy" in plan:
        lines.append(f"## Strategy\n\n{plan['strategy']}\n")

    if "phases" in plan and isinstance(plan["phases"], list):
        lines.append("## Phases\n")
        for phase in plan["phases"]:
            if isinstance(phase, dict):
                name = phase.get("name", "Phase")
                order = phase.get("order", "")
                prefix = f"{order}. " if order else "- "
                lines.append(f"{prefix}**{name}**")
                if phase.get("description"):
                    lines.append(f"  {phase['description']}")
                if phase.get("command"):
                    lines.append(f"  ```\n  {phase['command']}\n  ```")
                if phase.get("rationale"):
                    lines.append(f"  _{phase['rationale']}_")
                if phase.get("test_ids") and isinstance(phase["test_ids"], list):
                    lines.append(f"  Tests: {', '.join(phase['test_ids'][:10])}")
                if phase.get("tasks") and isinstance(phase["tasks"], list):
                    for t in phase["tasks"]:
                        if isinstance(t, dict):
                            bug = t.get("bug", "")
                            fix = t.get("fix", "")
                            lines.append(f"  - {bug}: {fix}" if bug else f"  - {t}")
                lines.append("")
            else:
                lines.append(f"- {phase}")
    elif not lines:
        try:
            lines.append(f"```json\n{json.dumps(plan, indent=2)}\n```")
        except (TypeError, ValueError):
            lines.append(str(plan))

    return "\n".join(lines)
