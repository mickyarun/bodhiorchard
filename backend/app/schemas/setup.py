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


class SetupGitHub(BaseModel):
    """GitHub integration settings."""

    model_config = {"populate_by_name": True}

    enabled: bool = False
    pat: str = Field(default="", alias="pat")


class SetupSlack(BaseModel):
    """Slack integration settings."""

    model_config = {"populate_by_name": True}

    enabled: bool = False
    bot_token: str = Field(default="", alias="botToken")
    signing_secret: str = Field(default="", alias="signingSecret")


class SetupSourceCode(BaseModel):
    """Local source code path configuration."""

    model_config = {"populate_by_name": True}

    local_path: str = Field(default="", alias="localPath")
    type: str = "single-repo"  # "single-repo" or "workspace"


class SetupIntegrations(BaseModel):
    """Integration settings for initial setup."""

    github: SetupGitHub = SetupGitHub()
    slack: SetupSlack = SetupSlack()


class SetupLLM(BaseModel):
    """LLM configuration for initial setup."""

    model_config = {"populate_by_name": True}

    provider: str = "ollama"
    model: str = "llama3:8b"
    base_url: str = Field(default="http://localhost:11434", alias="baseUrl")
    api_key: str = Field(default="", alias="apiKey")
    premium_provider: str = Field(default="ollama", alias="premiumProvider")
    premium_model: str = Field(default="llama3:70b", alias="premiumModel")
    embedding_provider: str = Field(default="ollama", alias="embeddingProvider")
    embedding_model: str = Field(default="nomic-embed-text", alias="embeddingModel")


class SetupAIConfig(BaseModel):
    """AI configuration selected in the setup wizard."""

    model_config = {"populate_by_name": True}

    preset: str = "hybrid"
    ollama_url: str = Field(default="http://localhost:11434", alias="ollamaUrl")
    ollama_model: str = Field(default="llama3:8b", alias="ollamaModel")
    cloud_provider: str = Field(default="anthropic", alias="cloudProvider")
    cloud_api_key: str = Field(default="", alias="cloudApiKey")
    cloud_model: str = Field(default="claude-sonnet-4-5-20250514", alias="cloudModel")


class SetupRequest(BaseModel):
    """Complete setup payload sent by the frontend wizard."""

    model_config = {"populate_by_name": True}

    organization: SetupOrganization
    admin: SetupAdmin
    source_code: SetupSourceCode = Field(default_factory=SetupSourceCode, alias="sourceCode")
    integrations: SetupIntegrations = SetupIntegrations()
    llm: SetupLLM = SetupLLM()
    ai_config: SetupAIConfig = Field(default_factory=SetupAIConfig, alias="aiConfig")


class SetupResponse(BaseModel):
    """Response after successful setup."""

    organization_id: str
    user_id: str
    access_token: str
    token_type: str = "bearer"
    message: str = "Setup complete"
    mcp_token: str | None = None


class DirectoryEntry(BaseModel):
    """A single directory entry returned by the browse endpoint."""

    name: str
    path: str
    is_git_repo: bool = False


class BrowseDirectoriesResponse(BaseModel):
    """Response from the directory browser endpoint."""

    current_path: str
    parent_path: str | None = None
    directories: list[DirectoryEntry] = []
