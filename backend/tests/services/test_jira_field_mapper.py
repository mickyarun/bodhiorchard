# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unit tests for the Jira field mapper and consolidator.

Pure-function tests — no database, no HTTP.
"""


from app.services.jira_consolidator import (
    ConsolidatedGroup,
    build_consolidated_requirements,
    consolidate_issues,
)
from app.services.jira_field_mapper import (
    JiraFieldMapper,
    build_user_cache_from_issues,
    get_parent_key,
    is_epic,
    is_subtask,
)

# ── Fixtures ──────────────────────────────────────────────────────


def _issue(
    key: str,
    summary: str = "Test",
    issue_type: str = "Story",
    status_name: str = "To Do",
    status_category: str = "new",
    priority: str = "Medium",
    parent_key: str | None = None,
    assignee_email: str | None = None,
    description: str | None = None,
) -> dict:
    """Build a minimal Jira issue dict for testing."""
    fields: dict = {
        "summary": summary,
        "issuetype": {"name": issue_type},
        "status": {
            "name": status_name,
            "statusCategory": {"key": status_category},
        },
        "priority": {"name": priority},
        "labels": [],
        "components": [],
        "fixVersions": [],
        "attachment": [],
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}
    if assignee_email:
        fields["assignee"] = {"emailAddress": assignee_email}
    if description:
        fields["description"] = description
    return {"key": key, "id": key.replace("-", ""), "fields": fields}


# ── Field Mapper Tests ────────────────────────────────────────────


class TestClassifyIssue:
    """Issue type classification."""

    def test_bug_classified_as_bug(self) -> None:
        mapper = JiraFieldMapper()
        assert mapper.classify_issue(_issue("X-1", issue_type="Bug")) == "bug"

    def test_story_classified_as_bud(self) -> None:
        mapper = JiraFieldMapper()
        assert mapper.classify_issue(_issue("X-1", issue_type="Story")) == "bud"

    def test_epic_classified_as_bud(self) -> None:
        mapper = JiraFieldMapper()
        assert mapper.classify_issue(_issue("X-1", issue_type="Epic")) == "bud"

    def test_task_classified_as_bud(self) -> None:
        mapper = JiraFieldMapper()
        assert mapper.classify_issue(_issue("X-1", issue_type="Task")) == "bud"

    def test_subtask_classified_as_bud(self) -> None:
        mapper = JiraFieldMapper()
        assert mapper.classify_issue(_issue("X-1", issue_type="Sub-task")) == "bud"

    def test_unknown_type_defaults_to_bud(self) -> None:
        mapper = JiraFieldMapper()
        assert mapper.classify_issue(_issue("X-1", issue_type="WeirdType")) == "bud"

    def test_user_override_skip(self) -> None:
        mapper = JiraFieldMapper(type_map={"story": "skip"})
        assert mapper.classify_issue(_issue("X-1", issue_type="Story")) == "skip"

    def test_user_override_case_insensitive(self) -> None:
        mapper = JiraFieldMapper(type_map={"BUG": "bud"})
        assert mapper.classify_issue(_issue("X-1", issue_type="Bug")) == "bud"


class TestStatusMapping:
    """BUD status mapping from Jira status."""

    def test_default_todo_maps_to_bud(self) -> None:
        mapper = JiraFieldMapper()
        fields = mapper.map_to_bud_fields(_issue("X-1", status_name="To Do"))
        assert fields["status"] == "bud"

    def test_default_in_progress_maps_to_development(self) -> None:
        mapper = JiraFieldMapper()
        fields = mapper.map_to_bud_fields(
            _issue("X-1", status_name="In Progress", status_category="indeterminate")
        )
        assert fields["status"] == "development"

    def test_default_done_maps_to_closed(self) -> None:
        mapper = JiraFieldMapper()
        fields = mapper.map_to_bud_fields(
            _issue("X-1", status_name="Done", status_category="done")
        )
        assert fields["status"] == "closed"

    def test_user_override_status(self) -> None:
        mapper = JiraFieldMapper(status_map={"in review": "testing"})
        fields = mapper.map_to_bud_fields(
            _issue("X-1", status_name="In Review", status_category="indeterminate")
        )
        assert fields["status"] == "testing"

    def test_falls_back_to_category(self) -> None:
        mapper = JiraFieldMapper()
        fields = mapper.map_to_bud_fields(
            _issue("X-1", status_name="CustomStatus", status_category="done")
        )
        assert fields["status"] == "closed"


class TestBugMapping:
    """Bug field mapping."""

    def test_severity_from_priority(self) -> None:
        mapper = JiraFieldMapper()
        highest = mapper.map_to_bug_fields(_issue("X-1", priority="Highest"))
        assert highest["severity"] == "critical"
        assert mapper.map_to_bug_fields(_issue("X-1", priority="High"))["severity"] == "high"
        assert mapper.map_to_bug_fields(_issue("X-1", priority="Medium"))["severity"] == "medium"
        assert mapper.map_to_bug_fields(_issue("X-1", priority="Low"))["severity"] == "low"
        assert mapper.map_to_bug_fields(_issue("X-1", priority="Lowest"))["severity"] == "low"

    def test_unknown_priority_defaults_medium(self) -> None:
        mapper = JiraFieldMapper()
        assert mapper.map_to_bug_fields(_issue("X-1", priority="Custom"))["severity"] == "medium"

    def test_bug_status_from_category(self) -> None:
        mapper = JiraFieldMapper()
        bug = mapper.map_to_bug_fields(
            _issue("X-1", status_name="Done", status_category="done")
        )
        assert bug["status"] == "closed"


class TestUserResolution:
    """Assignee email → UUID resolution via cache."""

    def test_known_user_resolved(self) -> None:
        mapper = JiraFieldMapper(user_cache={"alice@x.com": "uuid-123"})
        fields = mapper.map_to_bud_fields(
            _issue("X-1", assignee_email="alice@x.com")
        )
        assert fields["assignee_id"] == "uuid-123"

    def test_unknown_user_left_none(self) -> None:
        mapper = JiraFieldMapper(user_cache={})
        fields = mapper.map_to_bud_fields(
            _issue("X-1", assignee_email="unknown@x.com")
        )
        assert "assignee_id" not in fields

    def test_no_assignee(self) -> None:
        mapper = JiraFieldMapper()
        fields = mapper.map_to_bud_fields(_issue("X-1"))
        assert "assignee_id" not in fields


class TestMetadata:
    """Metadata JSONB construction."""

    def test_jira_key_preserved(self) -> None:
        mapper = JiraFieldMapper()
        fields = mapper.map_to_bud_fields(_issue("PROJ-42"))
        assert fields["metadata_"]["jira_key"] == "PROJ-42"
        assert fields["metadata_"]["source"] == "jira_import"

    def test_title_truncated_to_500(self) -> None:
        mapper = JiraFieldMapper()
        long_title = "A" * 600
        fields = mapper.map_to_bud_fields(_issue("X-1", summary=long_title))
        assert len(fields["title"]) == 500

    def test_no_description_placeholder(self) -> None:
        mapper = JiraFieldMapper()
        fields = mapper.map_to_bud_fields(_issue("X-1"))
        assert fields["requirements_md"] == "*No description provided in Jira.*"

    def test_plain_text_description(self) -> None:
        mapper = JiraFieldMapper()
        fields = mapper.map_to_bud_fields(_issue("X-1", description="Plain text"))
        assert fields["requirements_md"] == "Plain text"


# ── Utility Function Tests ────────────────────────────────────────


class TestUtilityFunctions:
    """Helper functions for issue introspection."""

    def test_get_parent_key(self) -> None:
        assert get_parent_key(_issue("X-1", parent_key="EPIC-1")) == "EPIC-1"
        assert get_parent_key(_issue("X-1")) is None

    def test_is_epic(self) -> None:
        assert is_epic(_issue("X-1", issue_type="Epic")) is True
        assert is_epic(_issue("X-1", issue_type="Story")) is False

    def test_is_subtask(self) -> None:
        assert is_subtask(_issue("X-1", issue_type="Sub-task")) is True
        assert is_subtask(_issue("X-1", issue_type="Story")) is False

    def test_build_user_cache_from_issues(self) -> None:
        issues = [
            _issue("X-1", assignee_email="Alice@X.com"),
            _issue("X-2", assignee_email="bob@x.com"),
            _issue("X-3"),  # No assignee
        ]
        emails = build_user_cache_from_issues(issues)
        assert "alice@x.com" in emails
        assert "bob@x.com" in emails
        assert len(emails) == 2


# ── Consolidator Tests ────────────────────────────────────────────


class TestEpicConsolidation:
    """Epic mode: group children under parent Epic."""

    def test_epic_with_children(self) -> None:
        mapper = JiraFieldMapper()
        issues = [
            _issue("EPIC-1", summary="Epic", issue_type="Epic"),
            _issue("STORY-1", summary="Story 1", parent_key="EPIC-1"),
            _issue("STORY-2", summary="Story 2", parent_key="EPIC-1"),
        ]
        groups, bugs = consolidate_issues(issues, mode="epic", mapper=mapper)
        assert len(groups) == 1
        assert len(groups[0].children) == 2
        assert len(bugs) == 0

    def test_orphan_story_becomes_standalone(self) -> None:
        mapper = JiraFieldMapper()
        issues = [
            _issue("STORY-1", summary="Orphan Story"),
        ]
        groups, bugs = consolidate_issues(issues, mode="epic", mapper=mapper)
        assert len(groups) == 1
        assert groups[0].primary.get("key") == "STORY-1"
        assert len(groups[0].children) == 0

    def test_bugs_separated(self) -> None:
        mapper = JiraFieldMapper()
        issues = [
            _issue("EPIC-1", summary="Epic", issue_type="Epic"),
            _issue("BUG-1", summary="Bug", issue_type="Bug", parent_key="EPIC-1"),
            _issue("BUG-2", summary="Standalone Bug", issue_type="Bug"),
        ]
        groups, standalone_bugs = consolidate_issues(issues, mode="epic", mapper=mapper)
        assert len(groups) == 1
        assert len(groups[0].bugs) == 1  # BUG-1 linked to EPIC-1
        assert len(standalone_bugs) == 1  # BUG-2 standalone

    def test_subtasks_folded(self) -> None:
        mapper = JiraFieldMapper()
        issues = [
            _issue("EPIC-1", summary="Epic", issue_type="Epic"),
            _issue("SUB-1", summary="Subtask", issue_type="Sub-task", parent_key="EPIC-1"),
        ]
        groups, _ = consolidate_issues(issues, mode="epic", mapper=mapper)
        assert len(groups[0].subtasks) == 1

    def test_skip_type_excluded(self) -> None:
        mapper = JiraFieldMapper(type_map={"task": "skip"})
        issues = [
            _issue("TASK-1", summary="Skipped", issue_type="Task"),
            _issue("STORY-1", summary="Kept"),
        ]
        groups, _ = consolidate_issues(issues, mode="epic", mapper=mapper)
        assert len(groups) == 1
        assert groups[0].primary.get("key") == "STORY-1"


class TestFlatConsolidation:
    """Flat mode: every non-bug issue is standalone."""

    def test_flat_mode_no_grouping(self) -> None:
        mapper = JiraFieldMapper()
        issues = [
            _issue("EPIC-1", summary="Epic", issue_type="Epic"),
            _issue("STORY-1", summary="Story 1"),
            _issue("BUG-1", summary="Bug", issue_type="Bug"),
        ]
        groups, bugs = consolidate_issues(issues, mode="flat", mapper=mapper)
        assert len(groups) == 2  # Epic + Story (each standalone)
        assert len(bugs) == 1


class TestBuildConsolidatedRequirements:
    """Markdown generation from consolidated groups."""

    def test_standalone_returns_description(self) -> None:
        mapper = JiraFieldMapper()
        group = ConsolidatedGroup(
            primary=_issue("X-1", summary="Test", description="Description here")
        )
        result = build_consolidated_requirements(group, mapper)
        assert "Description here" in result

    def test_epic_with_children_has_sections(self) -> None:
        mapper = JiraFieldMapper()
        group = ConsolidatedGroup(
            primary=_issue("EPIC-1", summary="Epic", description="Epic desc"),
            children=[
                _issue("STORY-1", summary="Story One", description="Story desc"),
            ],
            subtasks=[
                _issue("SUB-1", summary="Do thing"),
            ],
        )
        result = build_consolidated_requirements(group, mapper)
        assert "## Stories" in result
        assert "STORY-1: Story One" in result
        assert "Story desc" in result
        assert "## Sub-tasks" in result
        assert "- [ ] SUB-1: Do thing" in result

    def test_all_jira_keys(self) -> None:
        group = ConsolidatedGroup(
            primary=_issue("EPIC-1"),
            children=[_issue("S-1"), _issue("S-2")],
            subtasks=[_issue("T-1")],
            bugs=[_issue("B-1")],
        )
        keys = group.all_jira_keys
        assert set(keys) == {"EPIC-1", "S-1", "S-2", "T-1", "B-1"}
