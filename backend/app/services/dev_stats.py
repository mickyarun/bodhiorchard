"""Developer activity statistics and AI effectiveness scoring."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.bud_agent_task import BUDAgentTask
    from app.models.bud_commit import BUDCommit
    from app.models.dev_activity import DevActivityLog


def calculate_effectiveness(
    activities: list[DevActivityLog],
    commits: list[BUDCommit],
    agent_tasks: list[BUDAgentTask],
) -> dict[str, Any]:
    """Calculate AI effectiveness metrics from available data.

    Derives a composite score (0-100) from:
    - Self-reported confidence ratings (from MCP updates)
    - Agent task completion rate
    - Cost efficiency (cost per commit)

    Args:
        activities: DevActivityLog rows with metadata_.
        commits: BUDCommit rows.
        agent_tasks: BUDAgentTask rows with result_summary.

    Returns:
        Dict with score, confidence, completion_rate, cost_per_commit,
        test_coverage, and risk_count.
    """
    scores: list[float] = []

    # 1. Confidence avg from self-ratings
    confidences: list[int] = []
    latest_coverage = "none"
    risk_count = 0
    for a in activities:
        meta = getattr(a, "metadata_", None) or {}
        eff = meta.get("effectiveness", {})
        if eff.get("confidence"):
            confidences.append(int(eff["confidence"]))
        if eff.get("test_coverage"):
            latest_coverage = eff["test_coverage"]
        if eff.get("risks"):
            risk_count += len(eff["risks"])

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    if confidences:
        scores.append(avg_confidence / 10.0)

    # 2. Agent task completion rate
    completed = sum(1 for t in agent_tasks if getattr(t, "status", "") == "completed")
    total = len(agent_tasks)
    completion_rate = completed / total if total else 0.0
    if total:
        scores.append(completion_rate)

    # 3. Cost efficiency (lower cost per commit = better)
    total_cost = 0.0
    for t in agent_tasks:
        summary = getattr(t, "result_summary", None) or {}
        total_cost += summary.get("cost_usd", 0) or 0

    cost_per_commit = total_cost / len(commits) if commits else 0.0
    if commits and total_cost > 0:
        scores.append(max(0.0, 1.0 - cost_per_commit))

    overall = round((sum(scores) / len(scores)) * 100) if scores else 0

    return {
        "score": overall,
        "confidence": round(avg_confidence, 1),
        "completion_rate": round(completion_rate, 2),
        "cost_per_commit": round(cost_per_commit, 4),
        "total_cost_usd": round(total_cost, 4),
        "test_coverage": latest_coverage,
        "risk_count": risk_count,
    }
