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

"""Consolidate Jira issues into BUD-sized groups.

Handles three consolidation strategies:
- **epic**: Group children under their parent Epic into a single BUD
- **flat**: Every issue becomes its own BUD (1:1 mapping)
- Bugs are always separated into Bug records regardless of mode

Usage::

    groups = consolidate_issues(issues, mode="epic", mapper=mapper)
"""

from dataclasses import dataclass, field
from typing import Any, cast

import structlog

from app.services.jira_field_mapper import (
    JiraFieldMapper,
    get_parent_key,
    is_epic,
    is_subtask,
)

logger = structlog.get_logger(__name__)


@dataclass
class ConsolidatedGroup:
    """A group of Jira issues that will become a single BUD.

    Attributes:
        primary: The lead issue (Epic, or standalone Story/Task).
        children: Stories/tasks that belong to this Epic.
        subtasks: Sub-tasks folded into this group.
        bugs: Bug issues linked to this group (become Bug records).
    """

    primary: dict[str, Any]
    children: list[dict[str, Any]] = field(default_factory=list)
    subtasks: list[dict[str, Any]] = field(default_factory=list)
    bugs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_jira_keys(self) -> list[str]:
        """Return all Jira keys in this group."""
        keys = [self.primary.get("key", "")]
        keys.extend(c.get("key", "") for c in self.children)
        keys.extend(s.get("key", "") for s in self.subtasks)
        keys.extend(b.get("key", "") for b in self.bugs)
        return [k for k in keys if k]

    @property
    def primary_key(self) -> str:
        """Return the lead issue's Jira key."""
        return cast(str, self.primary.get("key", ""))


def consolidate_issues(
    issues: list[dict[str, Any]],
    *,
    mode: str = "epic",
    mapper: JiraFieldMapper,
) -> tuple[list[ConsolidatedGroup], list[dict[str, Any]]]:
    """Group issues into consolidated BUD groups and standalone bugs.

    Args:
        issues: List of raw Jira issue dicts.
        mode: ``"epic"`` (consolidate under epics) or ``"flat"`` (1:1).
        mapper: Field mapper for type classification.

    Returns:
        Tuple of (bud_groups, standalone_bugs).
        ``standalone_bugs`` are bugs with no parent Epic.
    """
    if mode == "flat":
        return _flat_consolidation(issues, mapper)
    return _epic_consolidation(issues, mapper)


def _epic_consolidation(
    issues: list[dict[str, Any]],
    mapper: JiraFieldMapper,
) -> tuple[list[ConsolidatedGroup], list[dict[str, Any]]]:
    """Consolidate: Epics absorb children; orphans stay standalone."""
    # Build Epic groups
    epic_groups: dict[str, ConsolidatedGroup] = {}
    orphans: list[dict[str, Any]] = []
    standalone_bugs: list[dict[str, Any]] = []

    # First pass: identify Epics
    for issue in issues:
        key = issue.get("key", "")
        if is_epic(issue):
            epic_groups[key] = ConsolidatedGroup(primary=issue)

    # Second pass: classify and assign children
    for issue in issues:
        key = issue.get("key", "")
        if is_epic(issue):
            continue  # Already handled

        target = mapper.classify_issue(issue)
        parent_key = get_parent_key(issue)

        # Guard: circular reference (issue is its own parent)
        if parent_key == key:
            parent_key = None

        if target == "bug":
            if parent_key and parent_key in epic_groups:
                epic_groups[parent_key].bugs.append(issue)
            else:
                standalone_bugs.append(issue)
            continue

        if target == "skip":
            continue

        # BUD-type issue: try to attach to parent Epic
        if parent_key and parent_key in epic_groups:
            if is_subtask(issue):
                epic_groups[parent_key].subtasks.append(issue)
            else:
                epic_groups[parent_key].children.append(issue)
        else:
            orphans.append(issue)

    # Convert orphans to standalone groups
    groups: list[ConsolidatedGroup] = list(epic_groups.values())
    for orphan in orphans:
        groups.append(ConsolidatedGroup(primary=orphan))

    logger.info(
        "jira_consolidation_complete",
        mode="epic",
        epic_groups=len(epic_groups),
        orphan_groups=len(orphans),
        standalone_bugs=len(standalone_bugs),
    )

    return groups, standalone_bugs


def _flat_consolidation(
    issues: list[dict[str, Any]],
    mapper: JiraFieldMapper,
) -> tuple[list[ConsolidatedGroup], list[dict[str, Any]]]:
    """Flat mode: every non-bug issue becomes its own BUD group."""
    groups: list[ConsolidatedGroup] = []
    standalone_bugs: list[dict[str, Any]] = []

    for issue in issues:
        target = mapper.classify_issue(issue)
        if target == "bug":
            standalone_bugs.append(issue)
        elif target == "skip":
            continue
        else:
            groups.append(ConsolidatedGroup(primary=issue))

    logger.info(
        "jira_consolidation_complete",
        mode="flat",
        groups=len(groups),
        standalone_bugs=len(standalone_bugs),
    )

    return groups, standalone_bugs


def build_consolidated_requirements(
    group: ConsolidatedGroup,
    mapper: JiraFieldMapper,
) -> str:
    """Build a rich requirements_md from a consolidated group.

    For Epics with children, produces structured Markdown with
    sub-sections per child story and a checklist for sub-tasks.
    For standalone issues, returns the primary's description.

    Args:
        group: The consolidated group.
        mapper: Field mapper for description conversion.

    Returns:
        Markdown string for the BUD's requirements_md.
    """
    primary_fields = mapper.map_to_bud_fields(group.primary)
    primary_desc = cast(str, primary_fields.get("requirements_md", ""))

    # Standalone issue — return description as-is
    if not group.children and not group.subtasks:
        return primary_desc

    parts: list[str] = []

    # Epic description
    if primary_desc and primary_desc != "*No description provided in Jira.*":
        parts.append(primary_desc)

    # Child stories as sub-sections
    if group.children:
        parts.append("## Stories")
        for child in group.children:
            child_key = child.get("key", "")
            child_fields = child.get("fields", {})
            child_summary = child_fields.get("summary", "Untitled")
            child_desc_raw = child_fields.get("description")
            child_desc = ""
            if isinstance(child_desc_raw, dict):
                from app.services.jira_adf_converter import adf_to_markdown

                child_desc = adf_to_markdown(child_desc_raw)
            elif child_desc_raw:
                child_desc = str(child_desc_raw)

            parts.append(f"### {child_key}: {child_summary}")
            if child_desc:
                parts.append(child_desc)

    # Sub-tasks as checklist
    if group.subtasks:
        parts.append("## Sub-tasks")
        for st in group.subtasks:
            st_key = st.get("key", "")
            st_summary = st.get("fields", {}).get("summary", "Untitled")
            st_status = (
                st.get("fields", {}).get("status", {}).get("statusCategory", {}).get("key", "")
            )
            checked = "x" if st_status == "done" else " "
            parts.append(f"- [{checked}] {st_key}: {st_summary}")

    return "\n\n".join(parts)
