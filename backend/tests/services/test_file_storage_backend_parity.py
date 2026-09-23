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

"""Backend parity: an upload policy behaves the same on S3 and local disk.

Deployments choose their storage backend with one env var, and the
default (local disk) is not the one production uses. That makes the two
paths easy to drift: a policy enforced on the way to disk but not on the
way to a bucket would only surface in production, on someone else's
install.

These pin the contract that matters — the policy gates before either
backend is chosen, and whatever it resolves is what gets stored, served
and deleted, byte-for-byte and type-for-type.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import FileStorageConfig
from app.services import file_storage as fs_module
from app.services.file_storage import FileStorage, FileStorageError
from app.services.upload_policy import bug_attachment_policy

POLICY = bug_attachment_policy(max_file_mb=10, max_files=10)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _local_storage(tmp_path: Path) -> FileStorage:
    return FileStorage(
        config=FileStorageConfig.model_construct(
            use_s3=False,
            s3_bucket="",
            s3_region="us-east-1",
            local_dir=str(tmp_path),
            aws_access_key_id="",
            aws_secret_access_key="",
            aws_session_token="",
        )
    )


def _s3_storage() -> FileStorage:
    return FileStorage(
        config=FileStorageConfig.model_construct(
            use_s3=True,
            s3_bucket="test-bucket",
            s3_region="us-east-1",
            local_dir="data/uploads",
            aws_access_key_id="",
            aws_secret_access_key="",
            aws_session_token="",
        )
    )


@pytest.fixture
def s3_client():  # type: ignore[no-untyped-def]
    """Patch ``aioboto3.Session`` and yield the fake S3 client."""
    s3 = MagicMock()
    s3.put_object = AsyncMock()
    s3.delete_object = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=s3)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.client = MagicMock(return_value=ctx)

    with patch.object(fs_module.aioboto3, "Session", MagicMock(return_value=session)):
        yield s3


# ── The policy gates before the backend is chosen ────────────────────


@pytest.mark.asyncio
async def test_s3_upload_carries_the_resolved_content_type(s3_client: MagicMock) -> None:
    """A spreadsheet reaches the bucket typed, not as octet-stream.

    S3 stores whatever ``ContentType`` we send and echoes it back on
    GET, so losing it here would make every downloaded ``.xlsx`` open as
    a binary blob for real users while tests on local disk stayed green.
    """
    await _s3_storage().upload(
        org_id="org-1",
        relative_path="bug-attachments/BUG-001/abc-export.xlsx",
        data=b"xl",
        content_type=XLSX,
        policy=POLICY,
    )

    kwargs = s3_client.put_object.await_args.kwargs
    assert kwargs["ContentType"] == XLSX
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "org-1/bug-attachments/BUG-001/abc-export.xlsx"
    assert kwargs["Body"] == b"xl"


@pytest.mark.asyncio
async def test_oversize_is_refused_before_s3_is_touched(s3_client: MagicMock) -> None:
    """The size cap must not depend on which backend is configured."""
    policy = bug_attachment_policy(max_file_mb=1, max_files=10)
    with pytest.raises(FileStorageError, match="1 MB limit"):
        await _s3_storage().upload(
            org_id="org-1",
            relative_path="bug-attachments/BUG-001/big.png",
            data=b"x" * (1024 * 1024 + 1),
            content_type="image/png",
            policy=policy,
        )
    s3_client.put_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_disallowed_type_is_refused_before_s3_is_touched(s3_client: MagicMock) -> None:
    """The type gate is the policy's, not the backend's."""
    with pytest.raises(FileStorageError, match="not allowed"):
        await _s3_storage().upload(
            org_id="org-1",
            relative_path="bug-attachments/BUG-001/payload.exe",
            data=b"MZ",
            content_type="application/x-msdownload",
            policy=POLICY,
        )
    s3_client.put_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_upload_refuses_the_same_oversize_file(tmp_path: Path) -> None:
    """Same cap, same message, other backend."""
    policy = bug_attachment_policy(max_file_mb=1, max_files=10)
    with pytest.raises(FileStorageError, match="1 MB limit"):
        await _local_storage(tmp_path).upload(
            org_id="org-1",
            relative_path="bug-attachments/BUG-001/big.png",
            data=b"x" * (1024 * 1024 + 1),
            content_type="image/png",
            policy=policy,
        )
    assert not list(tmp_path.rglob("*.png"))


# ── Local disk round-trips the bytes ─────────────────────────────────


@pytest.mark.asyncio
async def test_local_round_trip_preserves_bytes_and_layout(tmp_path: Path) -> None:
    """Upload → download → delete on the default backend.

    The org id prefixes the key on both backends, which is what keeps
    one tenant's uploads out of another's directory listing.
    """
    storage = _local_storage(tmp_path)
    payload = b"\x89PNG\r\n\x1a\n binary body"

    path = await storage.upload(
        org_id="org-1",
        relative_path="bug-attachments/BUG-001/abc-shot.png",
        data=payload,
        content_type="image/png",
        policy=POLICY,
    )
    assert path == "org-1/bug-attachments/BUG-001/abc-shot.png"
    assert (tmp_path / path).read_bytes() == payload

    data, _content_type = await storage.download(path)
    assert data == payload

    await storage.delete(path)
    assert not (tmp_path / path).exists()


@pytest.mark.asyncio
async def test_delete_is_idempotent_on_local_disk(tmp_path: Path) -> None:
    """A second delete must not raise.

    The attachment route removes the object before the row, so a retry
    after a partial failure deletes bytes that are already gone.
    """
    storage = _local_storage(tmp_path)
    path = await storage.upload(
        org_id="org-1",
        relative_path="bug-attachments/BUG-001/abc-shot.png",
        data=b"x",
        content_type="image/png",
        policy=POLICY,
    )
    await storage.delete(path)
    await storage.delete(path)


@pytest.mark.asyncio
async def test_s3_delete_targets_the_same_key(s3_client: MagicMock) -> None:
    """Deleting uses the stored path verbatim, so no orphan is left."""
    await _s3_storage().delete("org-1/bug-attachments/BUG-001/abc-shot.png")

    kwargs = s3_client.delete_object.await_args.kwargs
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "org-1/bug-attachments/BUG-001/abc-shot.png"
