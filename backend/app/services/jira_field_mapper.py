"""Map Jira issue fields to BUD and Bug model fields.

Pure-function module with no database or HTTP calls. Accepts raw
Jira JSON dicts and returns mapped Python dicts ready for ORM
construction. User resolution requires a pre-loaded email→UUID cache.

Usage::

    mapper = JiraFieldMapper(status_map=..., type_map=..., user_cache=...)
    mapped = mapper.map_issue(raw_jira_issue)
"""

from app.models.bud import BUDStatus
from app.models.bug import BugSeverity, BugStatus
from app.services.jira_adf_converter import adf_to_markdown

# Truncate very long descriptions to avoid DB bloat.
# Full text is preserved in metadata_.jira_full_description if truncated.
_MAX_DESCRIPTION_CHARS = 50_000

# ── Default status mapping ────────────────────────────────────────

# Maps Jira statusCategory.key → BUD status. Users can override
# individual status names in the import wizard.
_DEFAULT_CATEGORY_MAP: dict[str, str] = {
    "new": BUDStatus.BUD,
    "undefined": BUDStatus.BUD,
    "indeterminate": BUDStatus.DEVELOPMENT,
    "done": BUDStatus.CLOSED,
}

_DEFAULT_STATUS_NAME_MAP: dict[str, str] = {
    "to do": BUDStatus.BUD,
    "backlog": BUDStatus.BUD,
    "open": BUDStatus.BUD,
    "in progress": BUDStatus.DEVELOPMENT,
    "in development": BUDStatus.DEVELOPMENT,
    "in review": BUDStatus.CODE_REVIEW,
    "code review": BUDStatus.CODE_REVIEW,
    "in testing": BUDStatus.TESTING,
    "qa": BUDStatus.TESTING,
    "testing": BUDStatus.TESTING,
    "done": BUDStatus.CLOSED,
    "closed": BUDStatus.CLOSED,
    "resolved": BUDStatus.CLOSED,
}

# ── Priority → Bug severity ──────────────────────────────────────

_PRIORITY_SEVERITY_MAP: dict[str, str] = {
    "highest": BugSeverity.CRITICAL,
    "high": BugSeverity.HIGH,
    "medium": BugSeverity.MEDIUM,
    "low": BugSeverity.LOW,
    "lowest": BugSeverity.LOW,
}


# ── Mapper class ──────────────────────────────────────────────────


class JiraFieldMapper:
    """Stateless mapper from Jira issue JSON to BUD/Bug field dicts.

    Args:
        status_map: Optional user-provided Jira status name → BUD status overrides.
        type_map: Optional user-provided Jira issue type → target type overrides.
        user_cache: Pre-loaded mapping of lowercase email → Bodhiorchard user UUID string.
    """

    def __init__(
        self,
        *,
        status_map: dict[str, str] | None = None,
        type_map: dict[str, str] | None = None,
        user_cache: dict[str, str] | None = None,
    ) -> None:
        self._status_map = {k.lower(): v for k, v in (status_map or {}).items()}
        self._type_map = {k.lower(): v for k, v in (type_map or {}).items()}
        self._user_cache = user_cache or {}

    def classify_issue(self, issue: dict) -> str:
        """Determine target type for a Jira issue: 'bud', 'bug', or 'skip'.

        Priority:
        1. User-provided type_map override
        2. Jira issue type name matching
        """
        issue_type = _get_issue_type_name(issue).lower()

        # User override
        if issue_type in self._type_map:
            return self._type_map[issue_type]

        # Default classification
        if issue_type == "bug":
            return "bug"
        if issue_type in ("epic", "story", "task", "sub-task", "subtask"):
            return "bud"
        # Unknown types default to BUD
        return "bud"

    def map_to_bud_fields(self, issue: dict) -> dict:
        """Map a Jira issue to BUD model constructor kwargs.

        Returns dict with keys: title, status, requirements_md, metadata_.
        Does NOT include org_id, bud_number, or embedding (set by caller).
        """
        fields = issue.get("fields", {})

        title = (fields.get("summary") or "Untitled")[:500]
        description = self._convert_description(fields)
        status = self._resolve_bud_status(fields)
        assignee_id = self._resolve_user(fields.get("assignee"))

        metadata = self._build_metadata(issue, fields)

        # Truncate very long descriptions; preserve full text in metadata
        if len(description) > _MAX_DESCRIPTION_CHARS:
            metadata["jira_full_description_truncated"] = True
            description = (
                description[:_MAX_DESCRIPTION_CHARS] + "\n\n*[Truncated — full text too long]*"
            )

        result: dict = {
            "title": title,
            "status": status,
            "requirements_md": description or "*No description provided in Jira.*",
            "metadata_": metadata,
        }
        if assignee_id:
            result["assignee_id"] = assignee_id

        return result

    def map_to_bug_fields(self, issue: dict) -> dict:
        """Map a Jira Bug issue to Bug model constructor kwargs.

        Returns dict with keys: title, description, severity, status, module.
        Does NOT include org_id, reporter_id, or embedding (set by caller).
        """
        fields = issue.get("fields", {})

        title = (fields.get("summary") or "Untitled")[:500]
        description = self._convert_description(fields)
        severity = self._resolve_bug_severity(fields)
        status = self._resolve_bug_status(fields)
        assignee_id = self._resolve_user(fields.get("assignee"))

        # Use first component as module
        components = fields.get("components") or []
        module = components[0].get("name") if components else None

        result: dict = {
            "title": title,
            "description": description,
            "severity": severity,
            "status": status,
            "module": module,
        }
        if assignee_id:
            result["assignee_id"] = assignee_id

        return result

    def extract_comments(self, issue: dict) -> list[dict]:
        """Extract comments from a Jira issue for timeline events.

        Returns list of dicts with: author, body, created.
        """
        fields = issue.get("fields", {})
        comment_field = fields.get("comment", {})
        raw_comments = comment_field.get("comments", [])

        result: list[dict] = []
        for c in raw_comments:
            body_adf = c.get("body")
            body_md = adf_to_markdown(body_adf) if body_adf else c.get("body", "")
            author = c.get("author", {})
            result.append(
                {
                    "author": author.get("displayName", "Unknown"),
                    "author_email": author.get("emailAddress", ""),
                    "body": body_md,
                    "created": c.get("created", ""),
                }
            )
        return result

    # ── Internal helpers ──────────────────────────────────────────

    def _convert_description(self, fields: dict) -> str:
        """Convert description field (ADF or plain text) to Markdown."""
        desc = fields.get("description")
        if desc is None:
            return ""
        if isinstance(desc, dict):
            return adf_to_markdown(desc)
        return str(desc)

    def _resolve_bud_status(self, fields: dict) -> str:
        """Map Jira status to BUD status."""
        status_obj = fields.get("status") or {}
        status_name = (status_obj.get("name") or "").lower()
        category_key = status_obj.get("statusCategory", {}).get("key", "").lower()

        # 1. User override by exact status name
        if status_name in self._status_map:
            return self._status_map[status_name]

        # 2. Default name map
        if status_name in _DEFAULT_STATUS_NAME_MAP:
            return _DEFAULT_STATUS_NAME_MAP[status_name]

        # 3. Fall back to category
        return _DEFAULT_CATEGORY_MAP.get(category_key, BUDStatus.BUD)

    def _resolve_bug_status(self, fields: dict) -> str:
        """Map Jira status to Bug status."""
        status_obj = fields.get("status") or {}
        category_key = status_obj.get("statusCategory", {}).get("key", "").lower()
        if category_key == "done":
            return BugStatus.CLOSED
        if category_key == "indeterminate":
            return BugStatus.IN_PROGRESS
        return BugStatus.OPEN

    def _resolve_bug_severity(self, fields: dict) -> str:
        """Map Jira priority to Bug severity."""
        priority = fields.get("priority") or {}
        name = (priority.get("name") or "medium").lower()
        return _PRIORITY_SEVERITY_MAP.get(name, BugSeverity.MEDIUM)

    def _resolve_user(self, assignee: dict | None) -> str | None:
        """Resolve Jira assignee to Bodhiorchard user UUID via email cache."""
        if not assignee:
            return None
        email = (assignee.get("emailAddress") or "").lower()
        return self._user_cache.get(email)

    def _build_metadata(self, issue: dict, fields: dict) -> dict:
        """Build the metadata_ JSONB dict preserving original Jira data."""
        priority = fields.get("priority") or {}
        labels = fields.get("labels") or []
        components = [c.get("name") for c in (fields.get("components") or [])]
        fix_versions = [v.get("name") for v in (fields.get("fixVersions") or [])]
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        attachments = [
            {"filename": a.get("filename"), "url": a.get("content")}
            for a in (fields.get("attachment") or [])
        ]

        return {
            "source": "jira_import",
            "jira_key": issue.get("key", ""),
            "jira_id": issue.get("id", ""),
            "jira_priority": priority.get("name"),
            "jira_labels": labels,
            "jira_components": components,
            "jira_fix_versions": fix_versions,
            "jira_assignee_email": assignee.get("emailAddress"),
            "jira_reporter_email": reporter.get("emailAddress"),
            "jira_created": fields.get("created"),
            "jira_updated": fields.get("updated"),
            "jira_attachments": attachments if attachments else None,
        }


# ── Utility functions ─────────────────────────────────────────────


def _get_issue_type_name(issue: dict) -> str:
    """Extract the issue type name from a Jira issue dict."""
    return issue.get("fields", {}).get("issuetype", {}).get("name") or "Unknown"


def get_parent_key(issue: dict) -> str | None:
    """Extract the parent issue key (for Epic link or parent field)."""
    fields = issue.get("fields", {})
    # Jira Cloud uses "parent" for both Epic link and Sub-task parent
    parent = fields.get("parent")
    if parent:
        return parent.get("key")
    return None


def get_subtask_keys(issue: dict) -> list[str]:
    """Extract subtask keys from an issue."""
    fields = issue.get("fields", {})
    subtasks = fields.get("subtasks") or []
    return [s.get("key") for s in subtasks if s.get("key")]


def is_epic(issue: dict) -> bool:
    """Check if an issue is an Epic."""
    return _get_issue_type_name(issue).lower() == "epic"


def is_subtask(issue: dict) -> bool:
    """Check if an issue is a Sub-task."""
    return _get_issue_type_name(issue).lower() in ("sub-task", "subtask")


def build_user_cache_from_issues(issues: list[dict]) -> set[str]:
    """Extract all unique assignee/reporter emails from a batch of issues.

    Returns set of lowercase emails for bulk user resolution.
    """
    emails: set[str] = set()
    for issue in issues:
        fields = issue.get("fields", {})
        for field_name in ("assignee", "reporter"):
            person = fields.get(field_name)
            if person and person.get("emailAddress"):
                emails.add(person["emailAddress"].lower())
    return emails
