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

"""Pydantic schemas for the first-time setup endpoint."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.repo_install import BulkOnboardItem


class SetupOrganization(BaseModel):
    """Organization details for initial setup."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


class SetupAdmin(BaseModel):
    """Admin user details for initial setup."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class SetupRepo(BaseModel):
    """A single repo with branch mapping."""

    model_config = {"populate_by_name": True}

    path: str
    main_branch: str | None = Field(None, alias="mainBranch")
    develop_branch: str | None = Field(None, alias="developBranch")


class SetupSourceCode(BaseModel):
    """Local source code repositories with branch mappings."""

    model_config = {"populate_by_name": True}

    repos: list[SetupRepo] = Field(..., min_length=1)


class SetupScan(BaseModel):
    """Scan pipeline tuning settings for setup."""

    model_config = {"populate_by_name": True}

    timeout_seconds: int = Field(default=300, alias="timeoutSeconds", ge=60, le=1800)
    max_turns: int = Field(default=40, alias="maxTurns", ge=0, le=100)


class SetupClaude(BaseModel):
    """Claude Code auth choice collected in the setup wizard.

    ``host`` = trust the backend process env (Hybrid mode, or Full Docker
    with a compose-level ``ANTHROPIC_API_KEY``). ``api_key`` = Full Docker
    with a user-supplied key that will be stored encrypted on the org.
    """

    model_config = {"populate_by_name": True}

    auth_mode: str = Field(default="host", alias="authMode")
    api_key: str | None = Field(default=None, alias="apiKey")


class ClaudeCheckRequest(BaseModel):
    """Body for ``POST /api/setup/check-claude`` — optional provisional creds.

    Used by the setup wizard to validate a pasted API key *before* creating
    the org. When ``api_key`` is present the endpoint swaps it into the
    backend process env for the duration of the subprocess call, then
    restores whatever was there before.
    """

    model_config = {"populate_by_name": True}

    auth_mode: str = Field(default="host", alias="authMode")
    api_key: str | None = Field(default=None, alias="apiKey")


class SetupRequest(BaseModel):
    """Setup payload: org, admin, repos with branches, and scan settings."""

    model_config = {"populate_by_name": True}

    organization: SetupOrganization
    admin: SetupAdmin
    source_code: SetupSourceCode = Field(alias="sourceCode")
    scan: SetupScan = Field(default_factory=SetupScan)
    claude: SetupClaude = Field(default_factory=SetupClaude)


class SetupResponse(BaseModel):
    """Response after successful setup."""

    organization_id: str
    user_id: str
    access_token: str
    token_type: str = "bearer"
    message: str = "Setup complete"
    mcp_token: str | None = None
    scan_id: str | None = Field(None, alias="scanId")
    embedding_warning: str | None = Field(None, alias="embeddingWarning")

    model_config = {"populate_by_name": True}


class DirectoryEntry(BaseModel):
    """A single directory entry returned by the browse endpoint."""

    name: str
    path: str
    is_git_repo: bool = False
    has_sub_repos: bool = False


class BrowseDirectoriesResponse(BaseModel):
    """Response from the directory browser endpoint."""

    current_path: str
    parent_path: str | None = None
    directories: list[DirectoryEntry] = []


class InitOrgRequest(BaseModel):
    """Stage-1 wizard payload — provision the org + admin user only.

    Mirrors the org/admin/scan/claude sub-trees of :class:`SetupRequest`
    so existing wizard state can flow into this endpoint without a
    re-shape; just omit the ``sourceCode`` field. Repos are added in a
    separate stage via :class:`FinalizeWithReposRequest`.
    """

    model_config = ConfigDict(populate_by_name=True)

    organization: SetupOrganization
    admin: SetupAdmin
    scan: SetupScan = Field(default_factory=SetupScan)
    claude: SetupClaude = Field(default_factory=SetupClaude)


class InitOrgResponse(BaseModel):
    """Stage-1 wizard response — JWT to drive the rest of the flow."""

    model_config = ConfigDict(populate_by_name=True)

    organization_id: str = Field(alias="organizationId")
    user_id: str = Field(alias="userId")
    org_slug: str = Field(alias="orgSlug")
    access_token: str = Field(alias="accessToken")
    token_type: str = "bearer"
    mcp_token: str | None = Field(default=None, alias="mcpToken")
    is_setup_complete: bool = Field(default=False, alias="isSetupComplete")


class FinalizeWithReposRequest(BaseModel):
    """Stage-2 wizard payload — add repos via ONE OF two paths.

    - ``installable_items``: GitHub-App bulk-onboard path (async job).
    - ``source_code``: legacy paste-URL / local-path payload (sync scan).

    Exactly one of the two must be provided; the model validator below
    enforces the XOR.
    """

    model_config = ConfigDict(populate_by_name=True)

    installable_items: list[BulkOnboardItem] | None = Field(default=None, alias="installableItems")
    source_code: SetupSourceCode | None = Field(default=None, alias="sourceCode")

    @model_validator(mode="after")
    def _require_exactly_one_path(self) -> "FinalizeWithReposRequest":
        has_app = self.installable_items is not None and len(self.installable_items) > 0
        has_legacy = self.source_code is not None and len(self.source_code.repos) > 0
        if has_app == has_legacy:
            raise ValueError("Exactly one of 'installableItems' or 'sourceCode' must be provided.")
        return self


class FinalizeWithReposResponse(BaseModel):
    """Stage-2 wizard response — either a sync scan_id or an async job_id."""

    model_config = ConfigDict(populate_by_name=True)

    scan_id: str | None = Field(default=None, alias="scanId")
    job_id: str | None = Field(default=None, alias="jobId")
    is_setup_complete: bool = Field(default=True, alias="isSetupComplete")
    embedding_warning: str | None = Field(default=None, alias="embeddingWarning")


class SetupStatusResponse(BaseModel):
    """Response for the setup checklist status endpoint."""

    model_config = {"populate_by_name": True}

    org_created: bool = Field(alias="orgCreated")
    claude_code_tested: bool = Field(alias="claudeCodeTested")
    repo_added: bool = Field(alias="repoAdded")
    scan_complete: bool = Field(alias="scanComplete")
    scan_in_progress: bool = Field(alias="scanInProgress")
    scan_id: str | None = Field(None, alias="scanId")
    scan_progress: int = Field(0, alias="scanProgress")
    github_connected: bool = Field(alias="githubConnected")
    slack_connected: bool = Field(alias="slackConnected")
    branches_mapped: bool = Field(alias="branchesMapped")
    members_imported: bool = Field(alias="membersImported")
    qa_configured: bool = Field(False, alias="qaConfigured")
