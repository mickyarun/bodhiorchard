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

"""Result handlers for BUD agent tasks.

Each handler processes Claude's output, persists results to the database,
and optionally triggers follow-up actions (notifications, status transitions).
"""

import json
import re
import uuid as uuid_mod
from typing import Any

import structlog

from app.models.bud_agent_task import BUDAgentTask
from app.models.bud_feature_link import BUDFeatureLinkSource
from app.repositories.bud_feature_link import BUDFeatureLinkRepository

logger = structlog.get_logger(__name__)


async def handle_prd_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """PRD result: persist agent-declared feature links, then trigger estimation.

    The PM agent's final stdout message ends with a single JSON fence
    listing the existing-feature ids the requirement touches. We parse
    that fence, drop hallucinated / cross-org ids defensively, and
    upsert :class:`BUDFeatureLink` rows so downstream agents (Designer,
    TechPlanner, Code Reviewer, Tester) inherit the grounding.
    """
    linked_count = await _persist_pm_linked_features(bud_id, org_id, output, db)

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

    return {
        "section": "requirements_md",
        "output_length": len(output),
        "linked_feature_count": linked_count,
    }


async def _persist_pm_linked_features(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    db: Any,
) -> int:
    """Parse + persist ``linked_feature_ids`` from the PM agent's output.

    Returns the count of links actually accepted (after UUID parsing,
    org-scope filtering, and ON CONFLICT dedup at the repository).
    """
    parsed = _extract_last_json_dict(output)
    raw_ids = parsed.get("linked_feature_ids") if parsed else None
    if not isinstance(raw_ids, list):
        if parsed is not None:
            logger.warning(
                "pm_linked_feature_ids_missing_or_wrong_shape",
                bud_id=str(bud_id),
                fence_keys=list(parsed.keys()),
            )
        return 0

    valid_ids: list[uuid_mod.UUID] = []
    dropped: list[str] = []
    for raw in raw_ids:
        try:
            valid_ids.append(uuid_mod.UUID(str(raw)))
        except (ValueError, TypeError):
            dropped.append(str(raw))
    if dropped:
        logger.warning(
            "pm_linked_feature_ids_unparseable",
            bud_id=str(bud_id),
            dropped=dropped,
        )

    if not valid_ids:
        return 0

    link_repo = BUDFeatureLinkRepository(db, org_id=org_id)
    accepted = await link_repo.link_features(
        bud_id, valid_ids, source=BUDFeatureLinkSource.PM_AGENT
    )
    logger.info(
        "pm_linked_features_persisted",
        bud_id=str(bud_id),
        requested=len(valid_ids),
        accepted=len(accepted),
    )
    return len(accepted)


def _extract_last_json_dict(output: str) -> dict[str, Any] | None:
    """Return the dict parsed from the last ```json ... ``` fence in ``output``.

    Returns ``None`` when no fence is present or the contents don't
    parse as a JSON object. Reuses the same regex pattern as
    :func:`_extract_impacted_repos_json` for consistency — they look at
    the same kind of trailing-fence convention.
    """
    fences = list(re.finditer(r"```json\s*\n(.*?)\n\s*```", output, re.DOTALL))
    if not fences:
        return None
    try:
        parsed = json.loads(fences[-1].group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


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

        # Parse Implementation TODO section into BUDTodo records.
        # TODOs are created UNASSIGNED — the assignment agent distributes them
        # across developers when the BUD transitions to DEVELOPMENT phase
        # (see bud_assignment.auto_assign_for_phase). Failure here is
        # non-fatal — BUD still falls back to single-assignee flow.
        try:
            from app.services.todo_sync import sync_todos_from_tech_spec

            await sync_todos_from_tech_spec(
                db, org_id, bud.id, bud.tech_spec_md, default_assignee_id=None
            )
        except Exception:
            logger.warning("todo_sync_failed_after_tech_arch", bud_id=str(bud_id))

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
    """Code review result: parse JSON, sync any comments to GitHub.

    The code_review → testing transition is no longer owned by this handler.
    The happy path is driven by GitHub PR merges (see
    ``pr_auto_transition.check_all_prs_merged``) and the escape hatch is the
    ``POST /buds/{id}/code-review/override`` endpoint. This handler's only job
    is to persist the agent's first-run output: posting any inline comments
    to the linked GitHub PR via ``sync_review_comments_to_github``, which in
    turn writes them into ``bud.code_review_comments`` for the Code Review tab
    comment count.
    """
    from app.repositories.bud import BUDRepository

    review_data = _parse_code_review_output(output)
    parse_ok = review_data.get("_parse_ok", True)

    if not parse_ok:
        # Agent output was unparseable — log loudly with BUD context so on-call
        # can triage. The handler still returns successfully so the task row is
        # marked COMPLETED (a FAILED task would auto-retry and likely hit the
        # same parse failure), but the result_summary carries the parse_ok
        # flag so the UI can surface a "re-run code review" banner.
        logger.error(
            "code_review_parse_failed",
            bud_id=str(bud_id),
            task_id=str(task.id),
        )

    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    comment_count = 0

    if bud:
        raw_comments = review_data.get("code_review_comments", [])
        # Defensive: if the agent returned a scalar or garbage, don't crash
        # downstream with a confusing error.
        new_comments: list[dict] = raw_comments if isinstance(raw_comments, list) else []
        comment_count = len(new_comments)

        # Stash auto/manual test plan drafts in metadata for the testing phase
        # prompt builder to consume when that phase runs.
        auto_plan = review_data.get("automation_test_plan_md", "")
        manual_plan = review_data.get("manual_test_plan_md", "")
        if auto_plan or manual_plan:
            meta = dict(bud.metadata_ or {})
            meta["automation_test_plan_md"] = auto_plan
            meta["manual_test_plan_md"] = manual_plan
            bud.metadata_ = meta

        if new_comments:
            from app.services.github_pr_sync import sync_review_comments_to_github

            await sync_review_comments_to_github(bud_id, org_id, new_comments, db)

        await db.flush()

    return {
        "section": "test_plan_md",
        "comment_count": comment_count,
        "parse_ok": parse_ok,
    }


async def handle_testing_result(
    bud_id: uuid_mod.UUID,
    org_id: uuid_mod.UUID,
    output: str,
    task: BUDAgentTask,
    db: Any,
) -> dict | None:
    """Testing result: parse JSON and store test cases in BUD columns.

    When the org has QA automation disabled (``org.config.qa.enabled``
    is False), any automation cases the agent emits are dropped here —
    the prompt already tells the agent not to generate them, but this
    is the enforcement backstop so a misbehaving agent cannot populate
    automation cases against the org's will.
    """
    from app.repositories.bud import BUDRepository
    from app.repositories.organization import OrganizationRepository
    from app.services.json_parser import parse_json_response
    from app.services.org_settings import get_qa_settings

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

    # Single-point enforcement of the automation-off rule. Prompt tells the
    # agent what to do; this drops anything that slipped through.
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(org_id)
    qa = get_qa_settings(org.config if org else None)
    if not qa.enabled and parsed_data["automation_test_cases"]:
        logger.info(
            "qa_automation_disabled_dropping_cases",
            bud_id=str(bud_id),
            dropped=len(parsed_data["automation_test_cases"]),
        )
        parsed_data["automation_test_cases"] = []

    auto_empty = not parsed_data["automation_test_cases"]
    manual_empty = not parsed_data["manual_test_cases"]
    # Zero-cases warning is suppressed when automation is off and manual
    # cases exist — "automation empty, manual populated" is the expected
    # shape for automation-disabled orgs, not a failure.
    if output and auto_empty and manual_empty:
        logger.warning(
            "testing_output_zero_cases",
            bud_id=str(bud_id),
            task_id=str(task.id),
            output_length=len(output),
            output_preview=output[:500],
        )

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

    Returns the parsed dict on success, or a sentinel ``{"_parse_ok": False,
    "code_review_comments": []}`` on failure so the caller can distinguish
    "clean review with no issues" from "agent output was unparseable". A
    parse failure is logged at error level with a prefix of the raw output
    for forensics — silently treating unparseable output as "approved" is
    a safety hole in a code-review pipeline.
    """
    from app.services.json_parser import parse_json_response

    try:
        parsed = parse_json_response(output)
    except Exception as exc:
        logger.error(
            "code_review_output_parse_exception",
            error=str(exc),
            output_preview=(output or "")[:500],
        )
        return {"_parse_ok": False, "code_review_comments": []}

    if not isinstance(parsed, dict):
        logger.error(
            "code_review_output_not_dict",
            parsed_type=type(parsed).__name__,
            output_preview=(output or "")[:500],
        )
        return {"_parse_ok": False, "code_review_comments": []}

    parsed["_parse_ok"] = True
    return parsed


def _normalize_testing_output(parsed: dict[str, Any]) -> dict[str, Any]:
    """Normalize various agent output structures into expected format.

    The QA agent may produce test cases in several shapes:
    - ``{automation_test_cases: [...], manual_test_cases: [...]}`` (ideal)
    - ``{automation: [...], manual: [...]}`` (shorthand)
    - ``{test_cases: [{layer: "automation", ...}, {layer: "manual", ...}]}``
      (unified list with a ``layer`` discriminator)
    All are normalized into the canonical two-list shape.
    """
    auto = parsed.get("automation_test_cases", [])
    manual = parsed.get("manual_test_cases", [])
    plan = parsed.get("test_execution_plan", "")

    # Unified test_cases list with a discriminator per item. The agent has
    # used at least 3 different field names across runs (layer, type, suite),
    # so we check all known variants.
    if not auto and not manual and "test_cases" in parsed:
        all_cases = parsed["test_cases"]
        if isinstance(all_cases, list):
            for tc in all_cases:
                if not isinstance(tc, dict):
                    continue
                disc = (
                    tc.get("layer") or tc.get("type") or tc.get("suite") or tc.get("kind") or ""
                ).lower()
                if disc in ("automation", "automated", "auto", "unit", "integration", "component"):
                    auto.append(tc)
                else:
                    manual.append(tc)

    # Category-based fallback: if ALL test cases ended up as manual despite
    # the unified split (all discriminator fields were missing), re-classify
    # based on category heuristics. Unit/functional/boundary/negative tests
    # are typically automation; a11y/visual/ux tests are typically manual.
    auto_categories = {
        "functional",
        "boundary",
        "negative",
        "stress",
        "regression",
        "integration",
        "unit",
        "component",
        "impact",
    }
    if not auto and manual:
        reclassified_auto: list = []
        remaining_manual: list = []
        for tc in manual:
            cat = (tc.get("category") or "").lower()
            if cat in auto_categories:
                reclassified_auto.append(tc)
            else:
                remaining_manual.append(tc)
        if reclassified_auto:
            auto = reclassified_auto
            manual = remaining_manual

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

    # Post-process: replace raw Python list repr (['TC-001', 'TC-002'])
    # with comma-joined IDs. The agent sometimes embeds Python-style arrays
    # in the execution plan string.
    if isinstance(plan, str) and "['TC-" in plan:
        import re

        plan = re.sub(
            r"\['(TC-\d+)'(?:,\s*'(TC-\d+)')*\]",
            lambda m: ", ".join(s.strip("' ") for s in m.group(0).strip("[]").split(",")),
            plan,
        )

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
