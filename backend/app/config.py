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

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import instance_secrets


class DatabaseConfig(BaseSettings):
    """Database connection configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://bodhiorchard:bodhiorchard@localhost:5432/bodhiorchard",
        alias="DATABASE_URL",
    )


_DEV_SECRET_KEY = "change-me-in-production"
_DEV_ENCRYPTION_KEY = instance_secrets.LEGACY_ENCRYPTION_KEY


class AuthConfig(BaseSettings):
    """Authentication and JWT configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    secret_key: str = Field(default=_DEV_SECRET_KEY, alias="SECRET_KEY")
    encryption_key: str = Field(
        default=_DEV_ENCRYPTION_KEY,
        alias="ENCRYPTION_KEY",
        description="Key used to encrypt secrets (PATs, tokens) at rest in the database.",
    )
    encryption_key_previous: str = Field(
        default="",
        alias="ENCRYPTION_KEY_PREVIOUS",
        description="Comma-separated older ENCRYPTION_KEYs, still readable during a rotation.",
    )
    environment: str = Field(default="dev", alias="ENV")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    algorithm: str = "HS256"

    @model_validator(mode="after")
    def _use_instance_secrets(self) -> "AuthConfig":
        """Full Docker: take the generated keys when none are set.

        The old shared default stays readable as a previous key, so tokens
        still under it are re-encrypted rather than lost.
        """
        if not instance_secrets.enabled():
            return self
        if self.secret_key in ("", _DEV_SECRET_KEY):
            self.secret_key = instance_secrets.read("secret_key") or self.secret_key
        if self.encryption_key in ("", _DEV_ENCRYPTION_KEY):
            self.encryption_key = instance_secrets.read("encryption_key") or self.encryption_key
        previous = [k.strip() for k in self.encryption_key_previous.split(",") if k.strip()]
        if self.encryption_key != _DEV_ENCRYPTION_KEY and _DEV_ENCRYPTION_KEY not in previous:
            self.encryption_key_previous = ",".join([*previous, _DEV_ENCRYPTION_KEY])
        return self

    @model_validator(mode="after")
    def _reject_dev_secrets_in_prod(self) -> "AuthConfig":
        """Refuse to run with empty or dev-default secrets when ENV=production.

        An empty or well-known ``SECRET_KEY`` makes every JWT forgeable, and
        a default ``ENCRYPTION_KEY`` means the "encrypted" integration
        secrets are readable by anyone with the source. Compose passes
        ``${SECRET_KEY}`` through, so a missing env entry arrives as ``""``.
        """
        # Read through the settings field so ``ENV`` set in ``.env`` counts.
        if self.environment.lower() != "production":
            return self
        weak = [
            name
            for name, value, default in (
                ("SECRET_KEY", self.secret_key, _DEV_SECRET_KEY),
                ("ENCRYPTION_KEY", self.encryption_key, _DEV_ENCRYPTION_KEY),
            )
            if not value.strip() or value == default
        ]
        if weak:
            raise ValueError(
                f"{', '.join(weak)} must be set to a non-default value when "
                "ENV=production. Refusing to start.",
            )
        return self


class HRCryptoConfig(BaseSettings):
    """The key for employees' sensitive details and documents.

    Separate from ``ENCRYPTION_KEY`` so leaking the integration-secret key
    doesn't also expose PAN, Aadhaar, bank accounts and ID documents.
    ``HR_ENCRYPTION_KEYS`` is a comma-separated keyring of ``kid:base64key``
    entries (32-byte keys), newest first: new data uses the first; older
    entries stay readable until ``scripts/rotate_hr_keys.py`` re-encrypts.
    """

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    hr_encryption_keys: SecretStr = Field(default=SecretStr(""), alias="HR_ENCRYPTION_KEYS")
    environment: str = Field(default="dev", alias="ENV")

    @model_validator(mode="after")
    def _require_key_in_prod(self) -> "HRCryptoConfig":
        """Refuse to start in production without an HR key.

        Without one the HR routes answer 503 rather than store plaintext;
        in production that should never be a surprise discovered by HR.
        """
        if (
            self.environment.lower() == "production"
            and not self.hr_encryption_keys.get_secret_value().strip()
        ):
            raise ValueError(
                "HR_ENCRYPTION_KEYS must be set when ENV=production. Refusing to start."
            )
        return self


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
    def _use_instance_secret(self) -> "ColyseusConfig":
        """Full Docker: take the generated bridge secret when none is set."""
        if self.bridge_secret in ("", _DEV_BRIDGE_SECRET):
            generated = instance_secrets.read(
                "colyseus_bridge_secret", directory_env="BRIDGE_SECRET_DIR"
            )
            self.bridge_secret = generated or self.bridge_secret
        return self

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
    hr_crypto: HRCryptoConfig = HRCryptoConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    redis: RedisConfig = RedisConfig()
    integrations: IntegrationConfig = IntegrationConfig()
    storage: StorageConfig = StorageConfig()
    file_storage: FileStorageConfig = FileStorageConfig()
    ws: WebSocketConfig = WebSocketConfig()
    colyseus: ColyseusConfig = ColyseusConfig()


settings = Settings()
