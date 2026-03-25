"""Application configuration loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database connection configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://bodhigrove:bodhigrove@localhost:5432/bodhigrove",
        alias="DATABASE_URL",
    )


class AuthConfig(BaseSettings):
    """Authentication and JWT configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    encryption_key: str = Field(
        default="change-me-encryption-key",
        alias="ENCRYPTION_KEY",
        description="Key used to encrypt secrets (PATs, tokens) at rest in the database.",
    )
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    algorithm: str = "HS256"


class LLMConfig(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    provider: str = Field(default="ollama")
    model: str = Field(default="llama3:8b")
    base_url: str = Field(default="http://localhost:11434")
    premium_provider: str = Field(default="ollama")
    premium_model: str = Field(default="llama3:70b")
    merge_batch_size: int = Field(default=500, description="Max features per LLM merge call")
    merge_model: str = Field(
        default="claude-opus-4-6",
        description="Model for cross-repo feature merge (critical accuracy step)",
    )


class EmbeddingConfig(BaseSettings):
    """Embedding provider configuration."""

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_", env_file=".env", extra="ignore")

    provider: str = Field(default="fastembed")
    model: str = Field(default="BAAI/bge-small-en-v1.5")
    dimensions: int = Field(default=384)


class RedisConfig(BaseSettings):
    """Redis connection configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")


class WebSocketConfig(BaseSettings):
    """WebSocket real-time push configuration."""

    model_config = SettingsConfigDict(env_prefix="WS_", env_file=".env", extra="ignore")

    heartbeat_interval: int = Field(
        default=30,
        description="Seconds between server keepalive pongs.",
    )
    max_send_queue: int = Field(
        default=128,
        description="Max queued outbound messages per WS connection before dropping.",
    )
    max_subscribe_queue: int = Field(
        default=32,
        description="Max queued events per event-bus subscriber before dropping.",
    )


class IntegrationConfig(BaseSettings):
    """Third-party integration configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    github_pat: str = Field(default="", alias="GITHUB_PAT")
    slack_bot_token: str = Field(default="", alias="SLACK_BOT_TOKEN")
    slack_signing_secret: str = Field(default="", alias="SLACK_SIGNING_SECRET")


class Settings(BaseSettings):
    """Root application settings aggregating all config groups."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    public_url: str = Field(
        default="http://localhost:8000",
        alias="PUBLIC_URL",
        description="Public base URL for the backend (e.g. Slack webhooks, git hooks)",
    )
    frontend_url: str = Field(
        default="http://localhost:5173",
        alias="FRONTEND_URL",
        description="Public base URL for the frontend (used in login links, emails, Slack DMs)",
    )
    mcp_backend_url: str = Field(
        default="http://localhost:8000",
        alias="MCP_BACKEND_URL",
        description="Internal URL the MCP bridge uses to reach this backend (always localhost).",
    )

    db: DatabaseConfig = DatabaseConfig()
    auth: AuthConfig = AuthConfig()
    llm: LLMConfig = LLMConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    redis: RedisConfig = RedisConfig()
    integrations: IntegrationConfig = IntegrationConfig()
    ws: WebSocketConfig = WebSocketConfig()


settings = Settings()
