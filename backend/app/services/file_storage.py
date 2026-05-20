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

"""File storage abstraction: local folder by default, S3 if configured.

Provides a unified interface for uploading, downloading, and deleting files.
Storage backend is selected via environment variables at startup.
"""

from pathlib import Path

import aioboto3
import structlog
from botocore.exceptions import BotoCoreError, ClientError

from app.config import FileStorageConfig, settings

logger = structlog.get_logger(__name__)

# Maximum file size: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed MIME types for evidence uploads
ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "video/mp4",
    "video/webm",
}


class FileStorageError(Exception):
    """Raised when a file storage operation fails."""


class FileStorage:
    """File storage with local-disk default and optional S3 backend."""

    def __init__(self, config: FileStorageConfig | None = None) -> None:
        """Initialise with a config, defaulting to the global singleton.

        Args:
            config: An explicit :class:`FileStorageConfig`, typically
                only passed by tests that want to bypass the module-level
                ``settings`` singleton. ``None`` (the production path)
                reads ``app.config.settings.file_storage``, which itself
                flows through pydantic-settings so the ``.env`` file is
                actually loaded — calling ``os.getenv()`` directly (the
                prior implementation) silently ignored ``.env`` entries
                because ``BaseSettings.model_config[env_file]`` does NOT
                mutate ``os.environ``, it only populates the Settings
                instance. The symptom of that bug was "I set
                ``FILE_STORAGE_S3=true`` in ``.env`` but the backend
                keeps writing to disk."

        Raises:
            FileStorageError: when ``use_s3`` is enabled without a
                bucket name. Catching this at construction time
                surfaces the misconfig as a startup-time error log
                instead of an opaque boto3 ``ParamValidationError`` on
                the first user-triggered upload.
        """
        cfg = config if config is not None else settings.file_storage
        self.use_s3 = cfg.use_s3
        self.s3_bucket = cfg.s3_bucket
        self.s3_region = cfg.s3_region
        self.local_dir = cfg.local_dir

        # Log BEFORE the bucket-presence check so a misconfigured boot
        # leaves an "I tried this" breadcrumb in the logs alongside the
        # raise below — operator can see both the bucket value (empty)
        # and the error in one place instead of correlating two events.

        # One-shot INFO log at construction so the resolved backend is
        # visible in boot logs without needing to flip log levels. The
        # singleton is built lazily on first ``get_file_storage()``,
        # which is during the lifespan startup hook — every operator
        # complaint of the shape "I enabled S3 but nothing happens"
        # is answerable by grepping this single line.
        logger.info(
            "file_storage_resolved",
            backend="s3" if self.use_s3 else "local",
            s3_bucket=self.s3_bucket or None,
            s3_region=self.s3_region if self.use_s3 else None,
            local_dir=self.local_dir if not self.use_s3 else None,
        )

        if self.use_s3 and not self.s3_bucket:
            raise FileStorageError(
                "FILE_STORAGE_S3=true but FILE_STORAGE_S3_BUCKET is empty. "
                "Set the bucket name in the backend env or disable S3."
            )

    async def upload(
        self,
        org_id: str,
        relative_path: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Upload a file and return the storage path.

        Args:
            org_id: Organization UUID string for namespacing.
            relative_path: Path within the org namespace (e.g., qa-evidence/bud-id/tc-id/file.png).
            data: Raw file bytes.
            content_type: MIME type of the file.

        Returns:
            The storage path (local path or S3 key).

        Raises:
            FileStorageError: If file is too large or MIME type is not allowed.
        """
        if len(data) > MAX_FILE_SIZE:
            raise FileStorageError(
                f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB"
            )

        if content_type not in ALLOWED_MIME_TYPES:
            raise FileStorageError(
                f"MIME type '{content_type}' is not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            )

        full_path = f"{org_id}/{relative_path}"

        if self.use_s3:
            return await self._upload_s3(full_path, data, content_type)
        return await self._upload_local(full_path, data)

    async def download(self, storage_path: str) -> tuple[bytes, str]:
        """Download a file and return (data, content_type).

        Args:
            storage_path: The path returned by upload().

        Returns:
            Tuple of (file_bytes, content_type).

        Raises:
            FileStorageError: If the file is not found.
        """
        if self.use_s3:
            return await self._download_s3(storage_path)
        return await self._download_local(storage_path)

    async def delete(self, storage_path: str) -> None:
        """Delete a file from storage.

        Args:
            storage_path: The path returned by upload().
        """
        if self.use_s3:
            await self._delete_s3(storage_path)
        else:
            await self._delete_local(storage_path)

    # ── Local storage ────────────────────────────────────────────

    def _safe_local_path(self, relative_path: str) -> Path:
        """Resolve a path and verify it stays within the storage directory."""
        base = Path(self.local_dir).resolve()
        dest = (base / relative_path).resolve()
        if not str(dest).startswith(str(base)):
            raise FileStorageError("Invalid storage path: directory traversal detected")
        return dest

    async def _upload_local(self, full_path: str, data: bytes) -> str:
        """Store file on local disk under self.local_dir."""
        dest = self._safe_local_path(full_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        # ``info`` (not ``debug``) so the active backend is visible at
        # default log verbosity. Matches the new info-level ``file_uploaded_s3``
        # — operators can grep either event to confirm which path ran.
        logger.info("file_uploaded_local", path=str(dest), size=len(data))
        return full_path

    async def _download_local(self, storage_path: str) -> tuple[bytes, str]:
        """Read file from local disk."""
        import mimetypes

        dest = self._safe_local_path(storage_path)
        if not dest.exists():
            raise FileStorageError(f"File not found: {storage_path}")

        content_type = mimetypes.guess_type(str(dest))[0] or "application/octet-stream"
        return dest.read_bytes(), content_type

    async def _delete_local(self, storage_path: str) -> None:
        """Delete file from local disk."""
        dest = self._safe_local_path(storage_path)
        if dest.exists():
            dest.unlink()
            logger.debug("file_deleted_local", path=str(dest))

    # ── S3 storage ───────────────────────────────────────────────
    #
    # Every S3 op MUST wrap ``ClientError`` (and ``BotoCoreError`` for
    # credential / network failures that don't carry an HTTP status)
    # into a :class:`FileStorageError`. Without this, a misconfigured
    # backend — wrong region, missing IAM ``s3:PutObject``, the bucket
    # simply doesn't exist — propagates as a bare ``ClientError`` to
    # ``upload_evidence``, which only catches ``FileStorageError``.
    # FastAPI then turns it into an opaque 500 and the operator sees
    # "no image is getting stored" with no actionable hint.
    #
    # Logs are at ``info`` (success) / ``error`` (failure). Bumped
    # from the old ``debug`` so operators on default log levels can
    # confirm uploads landed without having to flip log verbosity.

    async def _upload_s3(self, full_path: str, data: bytes, content_type: str) -> str:
        """Store file in S3. Raises ``FileStorageError`` on any S3 failure."""
        session = aioboto3.Session()
        try:
            async with session.client("s3", region_name=self.s3_region) as s3:
                await s3.put_object(
                    Bucket=self.s3_bucket,
                    Key=full_path,
                    Body=data,
                    ContentType=content_type,
                )
        except (ClientError, BotoCoreError) as exc:
            logger.error(
                "file_upload_s3_failed",
                bucket=self.s3_bucket,
                region=self.s3_region,
                key=full_path,
                error_class=type(exc).__name__,
                error=str(exc),
            )
            raise FileStorageError(f"S3 upload failed ({type(exc).__name__}): {exc}") from exc
        logger.info("file_uploaded_s3", bucket=self.s3_bucket, key=full_path, size=len(data))
        return full_path

    async def _download_s3(self, storage_path: str) -> tuple[bytes, str]:
        """Read file from S3. Raises ``FileStorageError`` on any S3 failure."""
        session = aioboto3.Session()
        try:
            async with session.client("s3", region_name=self.s3_region) as s3:
                response = await s3.get_object(Bucket=self.s3_bucket, Key=storage_path)
                data = await response["Body"].read()
                content_type = response.get("ContentType", "application/octet-stream")
                return data, content_type
        except (ClientError, BotoCoreError) as exc:
            logger.error(
                "file_download_s3_failed",
                bucket=self.s3_bucket,
                region=self.s3_region,
                key=storage_path,
                error_class=type(exc).__name__,
                error=str(exc),
            )
            raise FileStorageError(f"S3 download failed ({type(exc).__name__}): {exc}") from exc

    async def _delete_s3(self, storage_path: str) -> None:
        """Delete a file from S3. Raises ``FileStorageError`` on any S3 failure."""
        session = aioboto3.Session()
        try:
            async with session.client("s3", region_name=self.s3_region) as s3:
                await s3.delete_object(Bucket=self.s3_bucket, Key=storage_path)
        except (ClientError, BotoCoreError) as exc:
            logger.error(
                "file_delete_s3_failed",
                bucket=self.s3_bucket,
                region=self.s3_region,
                key=storage_path,
                error_class=type(exc).__name__,
                error=str(exc),
            )
            raise FileStorageError(f"S3 delete failed ({type(exc).__name__}): {exc}") from exc
        logger.info("file_deleted_s3", bucket=self.s3_bucket, key=storage_path)


# Module-level singleton
_file_storage: FileStorage | None = None


def get_file_storage() -> FileStorage:
    """Get or create the singleton FileStorage instance."""
    global _file_storage  # noqa: PLW0603
    if _file_storage is None:
        _file_storage = FileStorage()
    return _file_storage
