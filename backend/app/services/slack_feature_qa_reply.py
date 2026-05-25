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

"""Slack mrkdwn reply formatters for feature Q&A answers."""

from app.models.bud import BUDDocument
from app.models.feature import Feature
from app.models.user import User


def format_bud_answer(
    bud: BUDDocument,
    assignee: User | None,
    frontend_url: str,
) -> str:
    """Format a BUD as a Slack mrkdwn reply.

    Args:
        bud: The BUD to format.
        assignee: Resolved assignee user, or None if unassigned / not linked.
        frontend_url: Base URL for the dashboard link (e.g. https://app.example.com).

    Returns:
        Slack mrkdwn formatted string.
    """
    bud_ref = f"BUD-{bud.bud_number:03d}"

    if assignee:
        assignee_str = (
            f"<@{assignee.slack_id}>" if assignee.slack_id else assignee.name or "Unassigned"
        )
    else:
        assignee_str = "Unassigned"

    date_str = "Not set"
    if bud.prod_p70_date:
        date_str = bud.prod_p70_date.strftime("%Y-%m-%d")
    elif bud.current_phase_deadline:
        date_str = f"Phase deadline {bud.current_phase_deadline.strftime('%Y-%m-%d')}"

    link = f"{frontend_url.rstrip('/')}/buds/{bud.bud_number}"

    return (
        f"*{bud_ref} — {bud.title}*\n"
        f"Status: `{bud.status}`  •  Assignee: {assignee_str}  •  Target: {date_str}\n"
        f"<{link}|View in dashboard>"
    )


def format_feature_answer(feature: Feature) -> str:
    """Format a Feature as a Slack mrkdwn reply.

    Args:
        feature: The Feature to format.

    Returns:
        Slack mrkdwn formatted string.
    """
    status_str = feature.feature_status or "tracked"
    ref_line = f"\nRef: {feature.source_ref}" if feature.source_ref else ""
    return (
        f"*{feature.feature_title}*\n"
        f"Status: `{status_str}`  •  Tracked in product backlog{ref_line}"
    )


def format_clarify_reply(question: str, candidates: list[dict]) -> str:  # type: ignore[type-arg]
    """Format a clarification prompt listing candidate matches.

    Args:
        question: The clarifying question to ask.
        candidates: List of candidate dicts with kind/bud_number/title fields.

    Returns:
        Slack mrkdwn formatted string.
    """
    lines = [question, ""]
    for c in candidates:
        if c.get("kind") == "bud":
            lines.append(f"• *BUD-{int(c['bud_number']):03d}* — {c.get('title', '')}")
        else:
            lines.append(f"• {c.get('title', '')}")
    return "\n".join(lines)
