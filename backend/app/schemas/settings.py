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

"""Pydantic schemas for the settings endpoints."""

import zoneinfo
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceCodeSettings(BaseModel):
    """Source code path configuration."""

    local_path: str = Field(default="", alias="localPath")
    type: str = "single-repo"

    model_config = {"populate_by_name": True}


class GitHubAppStatus(StrEnum):
    """Lifecycle of an org's GitHub App configuration.

    The bulk-import flow gates on this enum:

    - ``NOT_CONFIGURED``: no App ID and/or no private key — show the
      credentials form.
    - ``AWAITING_INSTALL``: credentials saved, but no installation_id
      yet — show the "Install on GitHub" CTA.
    - ``READY``: credentials + installation_id present — show the
      bulk-repo picker.

    The boolean ``GitHubSettings.connected`` is kept for back-compat
    and equals ``status != NOT_CONFIGURED``.
    """

    NOT_CONFIGURED = "not_configured"
    AWAITING_INSTALL = "awaiting_install"
    READY = "ready"


class GitHubSettings(BaseModel):
    """GitHub App integration settings (read response)."""

    enabled: bool = False
    connected: bool = False
    app_id: int | None = Field(None, alias="appId")
    has_private_key: bool = Field(False, alias="hasPrivateKey")
    installation_id: int | None = Field(None, alias="installationId")
    webhook_configured: bool = Field(False, alias="webhookConfigured")
    status: GitHubAppStatus = GitHubAppStatus.NOT_CONFIGURED
    slug: str | None = None
    install_url: str | None = Field(default=None, alias="installUrl")

    model_config = {"populate_by_name": True}


class GitHubAppUpdate(BaseModel):
    """GitHub App credentials for PATCH (accepts private key)."""

    app_id: int | None = Field(None, alias="appId")
    private_key: str | None = Field(None, alias="privateKey")
    webhook_secret: str | None = Field(None, alias="webhookSecret")
    installation_id: int | None = Field(None, alias="installationId")

    model_config = {"populate_by_name": True}


class SlackSettings(BaseModel):
    """Slack integration settings."""

    enabled: bool = False
    # `connected` is the source of truth for "does this org have Slack
    # credentials stored", independent of the user-controlled toggle.
    # The settings UI uses this to render the connected state so the
    # badge doesn't drift from the actual credential state in the DB.
    connected: bool = False
    bot_token: str = Field(default="", alias="botToken")
    signing_secret: str = Field(default="", alias="signingSecret")
    team_id: str = Field(default="", alias="teamId")

    model_config = {"populate_by_name": True}


class AIConfigSettings(BaseModel):
    """AI/LLM configuration."""

    preset: str = "claude-code"
    ollama_url: str = Field(default="http://localhost:11434", alias="ollamaUrl")
    ollama_model: str = Field(default="llama3:8b", alias="ollamaModel")
    cloud_provider: str = Field(default="anthropic", alias="cloudProvider")
    cloud_api_key: str = Field(default="", alias="cloudApiKey")
    cloud_model: str = Field(default="claude-sonnet-4-5-20250514", alias="cloudModel")
    merge_model_default: str | None = Field(
        default=None,
        alias="mergeModelDefault",
        description=(
            "Per-org override for the small-batch merge model. "
            "None = use platform default from LLMConfig."
        ),
    )
    merge_model_large: str | None = Field(
        default=None,
        alias="mergeModelLarge",
        description=(
            "Per-org override for the large-batch merge model. "
            "None = use platform default from LLMConfig."
        ),
    )

    model_config = {"populate_by_name": True}


class ScanSettings(BaseModel):
    """Scan pipeline tuning settings."""

    # Synth and merge each get their own timeout because the merge phase runs
    # one long Claude call over every active feature, while synth runs many
    # short calls in parallel — sharing a single ceiling forces a bad trade.
    timeout_seconds: int = Field(default=300, alias="timeoutSeconds", ge=60, le=3600)
    merge_timeout_seconds: int = Field(default=300, alias="mergeTimeoutSeconds", ge=60, le=3600)
    max_turns: int = Field(default=40, alias="maxTurns", ge=0, le=100)
    auto_create_members: bool = Field(
        default=True,
        alias="autoCreateMembers",
        description="Auto-create org members from git commit authors during scan.",
    )

    model_config = {"populate_by_name": True}


class QAAutomationSettings(BaseModel):
    """Org-level QA automation settings.

    The ``framework`` field flows directly into the QA agent system prompt
    via string substitution (see ``build_testing_prompt``). Because the
    agent runs with tool access, an unsanitized value like
    ``"Playwright. Ignore prior instructions and ..."`` is a prompt-injection
    vector. The regex below restricts the field to a small alphabet that
    can safely name a framework: ASCII letters, digits, space, underscore,
    plus, and hyphen, 1-40 chars. No newlines, quotes, backticks, or
    punctuation the agent could interpret as meta-instructions.
    """

    enabled: bool = True
    framework: str = Field(
        default="playwright",
        pattern=r"^[a-zA-Z0-9 _+\-]{1,40}$",
    )
    # When open bugs on a BUD in testing reach this count, the BUD is
    # auto-rejected back to development and the QA assignee is freed.
    bug_reject_threshold: int = Field(
        default=5,
        alias="bugRejectThreshold",
        ge=1,
        le=50,
    )

    model_config = {"populate_by_name": True}


class BUDStageSettings(BaseModel):
    """Org-level BUD lifecycle stage toggles.

    Only the UAT phase is toggle-able in v1. Other phases are required and
    cannot be skipped at org level.
    """

    uat_enabled: bool = Field(default=True, alias="uatEnabled")

    model_config = {"populate_by_name": True}


# Valid day-of-week keys for PresenceSettings.working_days.
WeekdayKey = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _default_working_days() -> list[WeekdayKey]:
    """Default working-days set — Monday through Friday."""
    return ["mon", "tue", "wed", "thu", "fri"]


class PresenceSettings(BaseModel):
    """Org-level presence-inference configuration.

    Controls how the Colyseus ``InferredPresenceSim`` and the Slack
    ``presence_cache._compute_state`` decide when a team member is at
    their desk, on a break, or at home. Defaults preserve the legacy
    behaviour (Mon-Fri, 08:00-18:00, server-local time) so existing orgs
    see no change until they explicitly save a setting.

    The ``timezone`` field is deliberately optional. ``None`` means
    "interpret times in the server's local zone" — this is the exact
    behaviour the two presence systems had before this setting existed
    and is the only default that guarantees zero behaviour change on
    un-migrated orgs. Setting a concrete IANA name (``"Asia/Kolkata"``,
    ``"America/New_York"``, ...) switches both systems into
    timezone-aware mode.
    """

    auto_mode_enabled: bool = Field(default=True, alias="autoModeEnabled")
    working_days: list[WeekdayKey] = Field(
        default_factory=_default_working_days,
        alias="workingDays",
        min_length=1,
    )
    working_hours_start: str = Field(
        default="08:00",
        alias="workingHoursStart",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    working_hours_end: str = Field(
        default="18:00",
        alias="workingHoursEnd",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    timezone: str | None = Field(default=None)

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """Reject unknown IANA timezone names. ``None`` is allowed.

        Uses ``ZoneInfo`` construction rather than ``available_timezones()`` so
        legacy aliases (e.g. ``Asia/Calcutta``) resolve consistently across
        hosts whose tz databases differ — Debian-slim images drop the
        ``backward`` zones into a separate ``tzdata-legacy`` package, while
        macOS ships them by default.
        """
        if value is None:
            return None
        try:
            zoneinfo.ZoneInfo(value)
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value!r}") from exc
        return value

    @model_validator(mode="after")
    def _start_before_end(self) -> "PresenceSettings":
        """Assert the working day's start time is strictly before its end."""

        def to_tuple(hhmm: str) -> tuple[int, int]:
            hour, minute = hhmm.split(":")
            return (int(hour), int(minute))

        if to_tuple(self.working_hours_start) >= to_tuple(self.working_hours_end):
            raise ValueError("working_hours_start must be strictly before working_hours_end")
        return self

    model_config = {"populate_by_name": True}


class ConnectionsRead(BaseModel):
    """Response schema for GET /settings/connections."""

    source_code: SourceCodeSettings = Field(default_factory=SourceCodeSettings, alias="sourceCode")
    github: GitHubSettings = GitHubSettings()
    slack: SlackSettings = SlackSettings()
    ai_config: AIConfigSettings = Field(default_factory=AIConfigSettings, alias="aiConfig")
    scan: ScanSettings = Field(default_factory=ScanSettings)
    qa_automation: QAAutomationSettings = Field(
        default_factory=QAAutomationSettings,
        alias="qaAutomation",
    )
    bud_stages: BUDStageSettings = Field(
        default_factory=BUDStageSettings,
        alias="budStages",
    )
    presence: PresenceSettings = Field(default_factory=PresenceSettings)
    jira: "JiraSettingsRead" = Field(default_factory=lambda: JiraSettingsRead())

    model_config = {"populate_by_name": True}


class RepoInfo(BaseModel):
    """Information about a tracked repository.

    The ``last_scan_*`` fields summarise the most recent ``ScanRepoRun``
    for this repo (across all scans). The Settings → Code list uses
    them to render a recency + status pill on rows that aren't part of
    the live in-flight scan, so the user can see at a glance which
    repos are stale, succeeded, or failed.
    """

    id: str
    path: str
    name: str
    status: str = "active"
    last_scanned: str | None = Field(None, alias="lastScanned")
    sha: str | None = None
    knowledge_count: int = Field(0, alias="knowledgeCount")
    feature_count: int = Field(0, alias="featureCount")
    main_branch: str | None = Field(None, alias="mainBranch")
    develop_branch: str | None = Field(None, alias="developBranch")
    uat_branch: str | None = Field(None, alias="uatBranch")
    has_uncommitted_changes: bool = Field(False, alias="hasUncommittedChanges")
    github_repo: str | None = Field(None, alias="githubRepo")
    setup_status: str = Field("not_setup", alias="setupStatus")
    # MCP setup-PR tracking. ``setup_pr_state`` is the authoritative
    # "PR is open / merged / closed" signal; ``setup_branch_pushed_at``
    # lets the UI distinguish "first scan never ran" from "branch on
    # origin but no PR" (App not configured). ``setup_compare_url`` is
    # derived server-side so the row component just needs an anchor.
    setup_branch_pushed_at: str | None = Field(None, alias="setupBranchPushedAt")
    setup_pr_url: str | None = Field(None, alias="setupPrUrl")
    setup_pr_number: int | None = Field(None, alias="setupPrNumber")
    setup_pr_state: Literal["open", "merged", "closed"] | None = Field(None, alias="setupPrState")
    setup_compare_url: str | None = Field(None, alias="setupCompareUrl")
    design_system_status: str = Field("none", alias="designSystemStatus")
    last_scan_status: str | None = Field(None, alias="lastScanStatus")
    last_scan_finished_at: str | None = Field(None, alias="lastScanFinishedAt")
    last_scan_started_at: str | None = Field(None, alias="lastScanStartedAt")
    last_scan_feature_count: int | None = Field(None, alias="lastScanFeatureCount")
    last_scan_id: str | None = Field(None, alias="lastScanId")
    # Per-repo classification + cross-layer link counts. Populated by the
    # ``classify_repo`` per-repo stage and the global ``backend_link``
    # phase. Optional so unscanned repos render a neutral row.
    repo_layer: str | None = Field(None, alias="repoLayer")
    tech_stack: str | None = Field(None, alias="techStack")
    db_flavor: str | None = Field(None, alias="dbFlavor")

    model_config = {"populate_by_name": True}


class RepoBranchUpdate(BaseModel):
    """Request to update a repository's branch mapping."""

    main_branch: str | None = Field(None, alias="mainBranch")
    develop_branch: str | None = Field(None, alias="developBranch")
    uat_branch: str | None = Field(None, alias="uatBranch")

    model_config = {"populate_by_name": True}


class RepoBranchList(BaseModel):
    """Response with available branches for a repository."""

    branches: list[str]
    current_main: str | None = Field(None, alias="currentMain")
    current_develop: str | None = Field(None, alias="currentDevelop")
    current_uat: str | None = Field(None, alias="currentUat")

    model_config = {"populate_by_name": True}


class AddRepoRequest(BaseModel):
    """Request to add a repository path."""

    path: str


class RepoStatusRequest(BaseModel):
    """Request to change a tracked repository's status."""

    status: str


class JiraSettings(BaseModel):
    """Jira Cloud connection settings for internal use (includes token).

    Used by ``get_jira_settings()`` to construct a ``JiraClient``.
    Never serialized directly to the frontend — use ``JiraSettingsRead``
    for API responses.
    """

    site_id: str = Field(default="", alias="siteId")
    site_url: str = Field(default="", alias="siteUrl")
    email: str = ""
    api_token: str = Field(default="", alias="apiToken")
    connected_at: str = Field(default="", alias="connectedAt")

    @property
    def is_connected(self) -> bool:
        """Return True if Jira credentials are configured."""
        return bool(self.site_url and self.email and self.api_token)

    model_config = {"populate_by_name": True}


class JiraSettingsRead(BaseModel):
    """Jira connection status for GET responses (token masked)."""

    enabled: bool = False
    site_url: str = Field(default="", alias="siteUrl")
    email: str = ""
    connected_at: str = Field(default="", alias="connectedAt")

    model_config = {"populate_by_name": True}


class JiraSettingsUpdate(BaseModel):
    """Jira credentials for PATCH (accepts token, never echoed back)."""

    site_url: str | None = Field(None, alias="siteUrl")
    email: str | None = None
    api_token: str | None = Field(None, alias="apiToken")

    model_config = {"populate_by_name": True}


class ConnectionsUpdate(BaseModel):
    """Request schema for PATCH /settings/connections.

    All fields are optional — only provided fields are updated.
    """

    source_code: SourceCodeSettings | None = Field(None, alias="sourceCode")
    github: GitHubAppUpdate | None = None
    slack: SlackSettings | None = None
    ai_config: AIConfigSettings | None = Field(None, alias="aiConfig")
    scan: ScanSettings | None = None
    qa_automation: QAAutomationSettings | None = Field(None, alias="qaAutomation")
    bud_stages: BUDStageSettings | None = Field(None, alias="budStages")
    presence: PresenceSettings | None = None
    jira: JiraSettingsUpdate | None = None

    model_config = {"populate_by_name": True}
