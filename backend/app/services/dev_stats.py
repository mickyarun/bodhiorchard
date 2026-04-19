# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Developer activity statistics and AI effectiveness scoring."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.bud_agent_task import BUDAgentTask
    from app.models.dev_activity import DevActivityLog


def calculate_effectiveness(
    activities: list[DevActivityLog],
    agent_tasks: list[BUDAgentTask],
) -> dict[str, Any]:
    """Calculate AI effectiveness metrics from hook activity data.

    Derives a composite score (0-100) from observable signals:
    - Success ratio (commits + file changes vs errors)
    - Agent task completion rate
    - Cost efficiency (cost per commit)

    Args:
        activities: DevActivityLog rows (all event types for a BUD).
        agent_tasks: BUDAgentTask rows with result_summary.

    Returns:
        Dict with score, confidence, completion_rate, cost_per_commit,
        test_coverage, and risk_count.
    """
    scores: list[float] = []

    # Count events by type
    commit_count = 0
    file_change_count = 0
    error_count = 0
    test_file_count = 0
    for a in activities:
        et = a.event_type
        if et == "commit":
            commit_count += 1
        elif et == "file_change":
            file_change_count += 1
            # Check if this is a test file
            fp = a.file_path or ""
            if "test" in fp.lower() or "spec" in fp.lower():
                test_file_count += 1
        elif et in ("tool_error", "api_error"):
            error_count += 1

    # 1. Confidence proxy: success ratio scaled to 0-10
    success = commit_count + file_change_count
    total_events = success + error_count
    confidence = (success / total_events * 10.0) if total_events > 0 else 0.0
    if total_events > 0:
        scores.append(confidence / 10.0)

    # 2. Test coverage: derived from file_change events touching test files
    if file_change_count > 0 and test_file_count > 0:
        test_ratio = test_file_count / file_change_count
        test_coverage = "full" if test_ratio >= 0.3 else "partial"
    else:
        test_coverage = "none"

    # 3. Risk count: number of error events
    risk_count = error_count

    # 4. Agent task completion rate
    from app.models.bud_agent_task import AgentTaskStatus

    completed = sum(1 for t in agent_tasks if t.status == AgentTaskStatus.COMPLETED)
    task_total = len(agent_tasks)
    completion_rate = completed / task_total if task_total else 0.0
    if task_total and (commit_count or file_change_count):
        scores.append(completion_rate)

    # 5. Cost efficiency (lower cost per commit = better)
    total_cost = 0.0
    for t in agent_tasks:
        summary = getattr(t, "result_summary", None) or {}
        total_cost += summary.get("cost_usd", 0) or 0

    cost_per_commit = total_cost / commit_count if commit_count else 0.0
    if commit_count and total_cost > 0:
        scores.append(max(0.0, 1.0 - cost_per_commit))

    overall = max(0, min(100, round((sum(scores) / len(scores)) * 100))) if scores else 0

    return {
        "score": overall,
        "confidence": round(confidence, 1),
        "completion_rate": round(completion_rate, 2),
        "cost_per_commit": round(cost_per_commit, 4),
        "total_cost_usd": round(total_cost, 4),
        "test_coverage": test_coverage,
        "risk_count": risk_count,
    }
