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

"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database connection configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://bodhiorchard:bodhiorchard@localhost:5432/bodhiorchard",
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
    merge_model_default: str = Field(
        default="claude-sonnet-4-6",
        description=(
            "Model for cross-repo feature merge at typical scale. "
            "Per-org override via org.config['llm']['merge_model_default']."
        ),
    )
    merge_model_large: str = Field(
        default="claude-opus-4-7",
        description=(
            "Escalation model for very large merge runs. "
            "Per-org override via org.config['llm']['merge_model_large']."
        ),
    )
    merge_safe_feature_budget: int = Field(
        default=16000,
        description=(
            "Active feature count above which the merge phase falls back "
            "to embedding-blocked clusters (Phase 4). At 1M-token context, "
            "16K features in a two-section prompt fits comfortably."
        ),
    )
    merge_sonnet_quality_budget: int = Field(
        default=3000,
        description=(
            "Active feature count at or below which Sonnet 4.6 handles "
            "the merge call; above this, Opus 4.7 is selected."
        ),
    )
    merge_large_cluster_opus: int = Field(
        default=200,
        description=(
            "Per-cluster feature count above which Opus 4.7 is selected "
            "for that cluster (Phase 4)."
        ),
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


def _detect_default_data_dir() -> str:
    """Pick the best ``data_dir`` default for the current host.

    Docker images mount a writable volume at ``/data``; the host (Hybrid
    mode) usually has a read-only ``/`` and no ``/data`` at all. We probe
    in that order so each deployment "just works" without requiring an
    env var:

    1. If ``/data`` exists and is writable → Docker volume is mounted.
    2. Otherwise → ``<repo-root>/repoclone``, a per-checkout dir at the
       repo root (one level above ``backend/``).

    Two constraints on the host-mode name:

    * Must live *outside* ``backend/`` — uvicorn's reload watcher
      unconditionally adds CWD to its watch list, so a data dir under
      ``backend/`` would trigger a reload on every clone or worktree
      pull and kill in-flight scans.
    * Must *not* start with ``.`` — graphify's ``collect_files`` walker
      drops any path whose absolute components include a dot-prefixed
      segment. A parent like ``.data`` would silently strip every
      source file from the indexer's input and produce empty graphs.
    """
    docker_path = Path("/data")
    if docker_path.is_dir() and os.access(docker_path, os.W_OK):
        return str(docker_path)
    repo_root = Path(__file__).resolve().parent.parent.parent
    return str(repo_root / "repoclone")


class StorageConfig(BaseSettings):
    """Filesystem layout for cloned repos, SSH keys, and other persistent state.

    A single ``data_dir`` env var controls the root; downstream services
    (``ssh_keys.py``, ``repo_cloner.py``, …) derive their subdirectories
    from it. This replaces the previously hardcoded ``/data`` paths that
    made Hybrid (host) mode crash with ``Read-only file system: '/data'``.
    """

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    data_dir: str = Field(
        default_factory=_detect_default_data_dir,
        alias="BODHIORCHARD_DATA_DIR",
        description=(
            "Root for cloned repos and SSH keys. Defaults to /data when running "
            "in the Docker image (writable volume mount) and to <backend>/.data "
            "on the host so Hybrid mode works without manual setup."
        ),
    )

    @property
    def ssh_dir(self) -> Path:
        """Per-installation SSH deploy keypair directory (mode 0700)."""
        return Path(self.data_dir) / "ssh"

    @property
    def repos_dir(self) -> Path:
        """Per-org cloned-repository root (``<data_dir>/repos/<org_slug>/...``)."""
        return Path(self.data_dir) / "repos"


class FileStorageConfig(BaseSettings):
    """File storage backend for QA evidence uploads (and other user files).

    Distinct from :class:`StorageConfig` above — which owns the *system*
    filesystem layout (cloned repos, SSH keys) — this one owns the
    *user-content* backend: local disk by default, S3 when
    ``FILE_STORAGE_S3=true``. ``os.getenv`` in the consumer is the
    historical anti-pattern that made ``.env``-only deployments
    silently fall back to local disk; routing through ``BaseSettings``
    matches the rest of the project and loads from ``.env`` correctly.
    """

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    use_s3: bool = Field(
        default=False,
        alias="FILE_STORAGE_S3",
        description=(
            "When true, uploads / downloads / deletes go through S3 "
            "instead of the local-disk backend."
        ),
    )
    s3_bucket: str = Field(
        default="",
        alias="FILE_STORAGE_S3_BUCKET",
        description="S3 bucket name. Required when use_s3 is true.",
    )
    s3_region: str = Field(
        default="us-east-1",
        alias="AWS_REGION",
        description="AWS region the S3 client connects to.",
    )
    local_dir: str = Field(
        default="data/uploads",
        alias="FILE_STORAGE_LOCAL_DIR",
        description=(
            "Root directory for the local-disk backend. "
            "Relative paths resolve against the backend's cwd."
        ),
    )

    # Explicit AWS credentials. Boto3's default chain (env vars →
    # ``~/.aws/credentials`` → IAM role) reads ``os.environ`` directly,
    # but pydantic-settings loads ``.env`` into the model instance
    # WITHOUT touching ``os.environ`` — same root cause as the
    # ``FILE_STORAGE_S3`` bug. Threading the keys through this config
    # and passing them to ``aioboto3.Session(...)`` explicitly means
    # ``.env``-only deployments behave the same as shell-env ones, and
    # explicit creds take precedence over the credentials file / IAM
    # role exactly as the boto3 chain documents. Leaving the fields
    # empty falls back to the default chain (omitting the args from
    # the ``Session`` call so boto3 picks up the file / role).
    aws_access_key_id: str = Field(
        default="",
        alias="AWS_ACCESS_KEY_ID",
        description="AWS access key. Takes precedence over ~/.aws/credentials and IAM role.",
    )
    aws_secret_access_key: str = Field(
        default="",
        alias="AWS_SECRET_ACCESS_KEY",
        description="AWS secret key paired with AWS_ACCESS_KEY_ID.",
    )
    aws_session_token: str = Field(
        default="",
        alias="AWS_SESSION_TOKEN",
        description="STS session token. Only needed for temporary credentials.",
    )


class IntegrationConfig(BaseSettings):
    """Third-party integration configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    slack_bot_token: str = Field(default="", alias="SLACK_BOT_TOKEN")
    slack_signing_secret: str = Field(default="", alias="SLACK_SIGNING_SECRET")


_DEV_BRIDGE_SECRET = "dev-colyseus-bridge-secret"


class ColyseusConfig(BaseSettings):
    """Colyseus multiplayer server bridge configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    url: str = Field(
        default="http://localhost:2567",
        alias="COLYSEUS_URL",
        description="HTTP base URL of the Colyseus multiplayer server (backend-to-server calls).",
    )
    bridge_secret: str = Field(
        default=_DEV_BRIDGE_SECRET,
        alias="COLYSEUS_BRIDGE_SECRET",
        description="Shared secret for backend ↔ Colyseus bridge authentication.",
    )

    @model_validator(mode="after")
    def _reject_dev_secret_in_prod(self) -> "ColyseusConfig":
        """Refuse to run with the dev default secret when ENV=production.

        The bridge grants anyone with the secret full authority to inject
        arbitrary dev/agent activity events into any org's garden — leaking
        the secret into source control would be catastrophic. In production
        the env var is mandatory; in dev/test the well-known default is
        acceptable for local tooling.
        """
        env = os.environ.get("ENV", "dev").lower()
        if env == "production" and self.bridge_secret == _DEV_BRIDGE_SECRET:
            raise ValueError(
                "COLYSEUS_BRIDGE_SECRET must be set to a non-default value "
                "when ENV=production. Refusing to start with the dev default.",
            )
        return self


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
    storage: StorageConfig = StorageConfig()
    file_storage: FileStorageConfig = FileStorageConfig()
    ws: WebSocketConfig = WebSocketConfig()
    colyseus: ColyseusConfig = ColyseusConfig()


settings = Settings()
