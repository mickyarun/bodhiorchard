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

import os
from pathlib import Path

import structlog

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

    def __init__(self) -> None:
        self.use_s3 = os.getenv("FILE_STORAGE_S3", "false").lower() == "true"
        self.s3_bucket = os.getenv("FILE_STORAGE_S3_BUCKET", "")
        self.s3_region = os.getenv("AWS_REGION", "us-east-1")
        self.local_dir = os.getenv("FILE_STORAGE_LOCAL_DIR", "data/uploads")

    def validate_config(self) -> None:
        """Fail-fast configuration check, called once at app startup.

        Runtime errors from a misconfigured backend land deep in an
        upload handler with cryptic ``aioboto3`` / ``boto3`` tracebacks
        the operator doesn't see until the first user-triggered upload.
        Better to refuse to start the process. Raises
        :class:`FileStorageError` so ``main.py`` lifespan can log and
        choose its policy (we currently log + continue, on the theory
        that an evidence-upload outage is non-fatal — but the loud log
        is the actionable signal).
        """
        if self.use_s3:
            if not self.s3_bucket:
                raise FileStorageError(
                    "FILE_STORAGE_S3=true but FILE_STORAGE_S3_BUCKET is empty. "
                    "Set the bucket name in the backend env or disable S3."
                )
            logger.info(
                "file_storage_configured",
                backend="s3",
                bucket=self.s3_bucket,
                region=self.s3_region,
            )
            return
        # Local backend: warn loudly when the path is inside the typical
        # container filesystem (``/app/...``) without a hint of being a
        # mount — that's the "Docker restart eats my evidence" footgun.
        # Operators on Hybrid mode point the dir at host-owned storage
        # and never see this warning.
        resolved = str(Path(self.local_dir).resolve())
        looks_ephemeral = resolved.startswith("/app/") and not resolved.startswith("/app/data/")
        logger.info(
            "file_storage_configured",
            backend="local",
            local_dir=resolved,
        )
        if looks_ephemeral:
            logger.warning(
                "file_storage_local_dir_may_be_ephemeral",
                local_dir=resolved,
                hint="Mount FILE_STORAGE_LOCAL_DIR as a Docker volume or "
                "set FILE_STORAGE_S3=true with a configured bucket.",
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
        logger.debug("file_uploaded_local", path=str(dest), size=len(data))
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

    async def _upload_s3(self, full_path: str, data: bytes, content_type: str) -> str:
        """Store file in S3."""
        import aioboto3

        session = aioboto3.Session()
        async with session.client("s3", region_name=self.s3_region) as s3:
            await s3.put_object(
                Bucket=self.s3_bucket,
                Key=full_path,
                Body=data,
                ContentType=content_type,
            )
        logger.debug("file_uploaded_s3", bucket=self.s3_bucket, key=full_path, size=len(data))
        return full_path

    async def _download_s3(self, storage_path: str) -> tuple[bytes, str]:
        """Read file from S3."""
        import aioboto3

        session = aioboto3.Session()
        async with session.client("s3", region_name=self.s3_region) as s3:
            try:
                response = await s3.get_object(Bucket=self.s3_bucket, Key=storage_path)
                data = await response["Body"].read()
                content_type = response.get("ContentType", "application/octet-stream")
                return data, content_type
            except Exception as exc:
                raise FileStorageError(f"S3 download failed: {storage_path}") from exc

    async def _delete_s3(self, storage_path: str) -> None:
        """Delete file from S3."""
        import aioboto3

        session = aioboto3.Session()
        async with session.client("s3", region_name=self.s3_region) as s3:
            await s3.delete_object(Bucket=self.s3_bucket, Key=storage_path)
            logger.debug("file_deleted_s3", bucket=self.s3_bucket, key=storage_path)


# Module-level singleton
_file_storage: FileStorage | None = None


def get_file_storage() -> FileStorage:
    """Get or create the singleton FileStorage instance."""
    global _file_storage  # noqa: PLW0603
    if _file_storage is None:
        _file_storage = FileStorage()
    return _file_storage
