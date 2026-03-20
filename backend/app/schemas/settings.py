"""Pydantic schemas for the settings endpoints."""

from pydantic import BaseModel, Field


class SourceCodeSettings(BaseModel):
    """Source code path configuration."""

    local_path: str = Field(default="", alias="localPath")
    type: str = "single-repo"

    model_config = {"populate_by_name": True}


class GitHubSettings(BaseModel):
    """GitHub integration settings."""

    enabled: bool = False
    pat: str = ""

    model_config = {"populate_by_name": True}


class SlackSettings(BaseModel):
    """Slack integration settings."""

    enabled: bool = False
    bot_token: str = Field(default="", alias="botToken")
    signing_secret: str = Field(default="", alias="signingSecret")

    model_config = {"populate_by_name": True}


class AIConfigSettings(BaseModel):
    """AI/LLM configuration."""

    preset: str = "hybrid"
    ollama_url: str = Field(default="http://localhost:11434", alias="ollamaUrl")
    ollama_model: str = Field(default="llama3:8b", alias="ollamaModel")
    cloud_provider: str = Field(default="anthropic", alias="cloudProvider")
    cloud_api_key: str = Field(default="", alias="cloudApiKey")
    cloud_model: str = Field(default="claude-sonnet-4-5-20250514", alias="cloudModel")

    model_config = {"populate_by_name": True}


class ScanSettings(BaseModel):
    """Scan pipeline tuning settings."""

    timeout_seconds: int = Field(default=300, alias="timeoutSeconds", ge=60, le=1800)
    max_turns: int = Field(default=40, alias="maxTurns", ge=0, le=100)

    model_config = {"populate_by_name": True}


class ConnectionsRead(BaseModel):
    """Response schema for GET /settings/connections."""

    source_code: SourceCodeSettings = Field(default_factory=SourceCodeSettings, alias="sourceCode")
    github: GitHubSettings = GitHubSettings()
    slack: SlackSettings = SlackSettings()
    ai_config: AIConfigSettings = Field(default_factory=AIConfigSettings, alias="aiConfig")
    scan: ScanSettings = Field(default_factory=ScanSettings)

    model_config = {"populate_by_name": True}


class RepoInfo(BaseModel):
    """Information about a tracked repository."""

    path: str
    name: str
    last_scanned: str | None = Field(None, alias="lastScanned")
    sha: str | None = None
    knowledge_count: int = Field(0, alias="knowledgeCount")
    feature_count: int = Field(0, alias="featureCount")

    model_config = {"populate_by_name": True}


class AddRepoRequest(BaseModel):
    """Request to add a repository path."""

    path: str


class ConnectionsUpdate(BaseModel):
    """Request schema for PATCH /settings/connections.

    All fields are optional — only provided fields are updated.
    """

    source_code: SourceCodeSettings | None = Field(None, alias="sourceCode")
    github: GitHubSettings | None = None
    slack: SlackSettings | None = None
    ai_config: AIConfigSettings | None = Field(None, alias="aiConfig")
    scan: ScanSettings | None = None

    model_config = {"populate_by_name": True}
