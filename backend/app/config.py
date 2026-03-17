"""Application configuration loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database connection configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://flowdev:flowdev@localhost:5432/flowdev",
        alias="DATABASE_URL",
    )


class AuthConfig(BaseSettings):
    """Authentication and JWT configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    algorithm: str = "HS256"


class LLMConfig(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    provider: str = Field(default="ollama")
    model: str = Field(default="llama3:8b")
    base_url: str = Field(default="http://localhost:11434")
    premium_provider: str = Field(default="ollama")
    premium_model: str = Field(default="llama3:70b")


class EmbeddingConfig(BaseSettings):
    """Embedding provider configuration."""

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_", env_file=".env", extra="ignore")

    provider: str = Field(default="ollama")
    model: str = Field(default="nomic-embed-text")
    dimensions: int = Field(default=768)


class RedisConfig(BaseSettings):
    """Redis connection configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")


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
        description="Public base URL for generating callback URLs (e.g. Slack webhooks)",
    )

    db: DatabaseConfig = DatabaseConfig()
    auth: AuthConfig = AuthConfig()
    llm: LLMConfig = LLMConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    redis: RedisConfig = RedisConfig()
    integrations: IntegrationConfig = IntegrationConfig()


settings = Settings()
