"""Pydantic schemas for the first-time setup endpoint."""

from pydantic import BaseModel, EmailStr, Field


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


class SetupRequest(BaseModel):
    """Setup payload: org, admin, repos with branches, and scan settings."""

    model_config = {"populate_by_name": True}

    organization: SetupOrganization
    admin: SetupAdmin
    source_code: SetupSourceCode = Field(alias="sourceCode")
    scan: SetupScan = Field(default_factory=SetupScan)


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
