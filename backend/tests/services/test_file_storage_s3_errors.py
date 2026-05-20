# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""S3 backend must surface errors as ``FileStorageError`` for the API layer.

Reported failure mode: operator sets ``FILE_STORAGE_S3=true``, uploads
an image, "no image is getting stored". Root cause was that
``_upload_s3`` let boto3 ``ClientError`` / ``BotoCoreError`` propagate
uncaught. ``bud_qa.upload_evidence`` only catches
:class:`FileStorageError`, so the underlying cause never reached the
HTTP response and never made it to a log line the operator would think
to grep for.

These tests pin the new contract: every S3 op wraps its boto3
exception into a ``FileStorageError`` carrying the original class
name + message, and logs a structured event the operator can find.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.services.file_storage import FileStorage, FileStorageError


def _client_error(code: str, op: str = "PutObject", message: str = "denied") -> ClientError:
    """Build a realistic boto3 ``ClientError`` for an S3 op."""
    return ClientError(
        {"Error": {"Code": code, "Message": message}, "ResponseMetadata": {}},
        op,
    )


def _s3_client_mock(method_to_raise: str | None = None, exc: Exception | None = None) -> MagicMock:
    """Return an ``aioboto3.Session().client('s3')`` lookalike.

    The context manager protocol is preserved so ``async with`` works,
    and the chosen method (``put_object`` / ``get_object`` / ``delete_object``)
    optionally raises ``exc``. Methods not under test return a benign mock.
    """
    s3 = MagicMock()
    s3.put_object = AsyncMock()
    s3.get_object = AsyncMock()
    s3.delete_object = AsyncMock()
    if method_to_raise and exc is not None:
        getattr(s3, method_to_raise).side_effect = exc

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=s3)
    ctx.__aexit__ = AsyncMock(return_value=None)

    client_factory = MagicMock(return_value=ctx)
    session = MagicMock()
    session.client = client_factory
    return session


@pytest.fixture
def fake_aioboto3() -> MagicMock:
    """Inject a fake ``aioboto3`` into ``sys.modules`` for the lazy import.

    Each S3 helper does ``import aioboto3`` at call time. In CI the real
    package is installed; locally and in CI alike we want to test
    behaviour against a controlled session mock instead of hitting AWS.
    Returning the ``Session`` MagicMock lets each test customise the
    client behaviour per-call.
    """
    fake = types.ModuleType("aioboto3")
    session_factory = MagicMock()
    fake.Session = session_factory  # type: ignore[attr-defined]
    sys.modules["aioboto3"] = fake
    yield session_factory
    sys.modules.pop("aioboto3", None)


def _enable_s3(monkeypatch: pytest.MonkeyPatch) -> FileStorage:
    monkeypatch.setenv("FILE_STORAGE_S3", "true")
    monkeypatch.setenv("FILE_STORAGE_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    return FileStorage()


# ── _upload_s3 ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "code",
    ["AccessDenied", "NoSuchBucket", "InvalidAccessKeyId", "SignatureDoesNotMatch"],
)
async def test_upload_wraps_client_error(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock, code: str
) -> None:
    storage = _enable_s3(monkeypatch)
    fake_aioboto3.return_value = _s3_client_mock("put_object", _client_error(code))
    with pytest.raises(FileStorageError) as excinfo:
        await storage._upload_s3("org/qa-evidence/x.png", b"data", "image/png")
    msg = str(excinfo.value)
    assert "S3 upload failed" in msg
    assert "ClientError" in msg
    assert code in msg


async def test_upload_wraps_network_error(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    # ``EndpointConnectionError`` is ``BotoCoreError``, not ``ClientError``.
    # The wrapping must catch BOTH branches — otherwise a wrong-region or
    # offline-S3 deployment would still leak the raw exception.
    storage = _enable_s3(monkeypatch)
    err = EndpointConnectionError(endpoint_url="https://s3.example/")
    fake_aioboto3.return_value = _s3_client_mock("put_object", err)
    with pytest.raises(FileStorageError) as excinfo:
        await storage._upload_s3("org/qa-evidence/x.png", b"data", "image/png")
    assert "EndpointConnectionError" in str(excinfo.value)


async def test_upload_happy_path_returns_key(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    storage = _enable_s3(monkeypatch)
    fake_aioboto3.return_value = _s3_client_mock()
    result = await storage._upload_s3("org/qa-evidence/x.png", b"data", "image/png")
    assert result == "org/qa-evidence/x.png"


async def test_upload_logs_structured_failure(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    # Operator looking at "no image is getting stored" must be able to grep
    # ``file_upload_s3_failed`` and see the bucket, region, key, and the
    # boto3 error code — otherwise the diagnostic round-trip is "open
    # logs, find nothing, escalate".
    storage = _enable_s3(monkeypatch)
    fake_aioboto3.return_value = _s3_client_mock("put_object", _client_error("AccessDenied"))

    from app.services import file_storage as mod

    captured: list[dict[str, object]] = []
    with (
        patch.object(mod.logger, "error", side_effect=lambda *a, **kw: captured.append(kw)),
        pytest.raises(FileStorageError),
    ):
        await storage._upload_s3("org/qa-evidence/x.png", b"data", "image/png")

    assert len(captured) == 1
    log_kwargs = captured[0]
    assert log_kwargs["bucket"] == "test-bucket"
    assert log_kwargs["region"] == "us-east-1"
    assert log_kwargs["key"] == "org/qa-evidence/x.png"
    assert log_kwargs["error_class"] == "ClientError"
    assert "AccessDenied" in str(log_kwargs["error"])


# ── _download_s3 ────────────────────────────────────────────────────


async def test_download_wraps_client_error(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    storage = _enable_s3(monkeypatch)
    fake_aioboto3.return_value = _s3_client_mock(
        "get_object", _client_error("NoSuchKey", op="GetObject")
    )
    with pytest.raises(FileStorageError) as excinfo:
        await storage._download_s3("org/qa-evidence/x.png")
    assert "S3 download failed" in str(excinfo.value)
    assert "ClientError" in str(excinfo.value)


# ── _delete_s3 ──────────────────────────────────────────────────────


async def test_delete_wraps_client_error(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    storage = _enable_s3(monkeypatch)
    fake_aioboto3.return_value = _s3_client_mock(
        "delete_object", _client_error("AccessDenied", op="DeleteObject")
    )
    with pytest.raises(FileStorageError) as excinfo:
        await storage._delete_s3("org/qa-evidence/x.png")
    assert "S3 delete failed" in str(excinfo.value)


async def test_delete_happy_path_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    storage = _enable_s3(monkeypatch)
    fake_aioboto3.return_value = _s3_client_mock()
    await storage._delete_s3("org/qa-evidence/x.png")  # must not raise
