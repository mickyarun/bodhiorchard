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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.config import FileStorageConfig
from app.services import file_storage as fs_module
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
def fake_aioboto3():  # type: ignore[no-untyped-def]
    """Patch ``aioboto3.Session`` on the ``file_storage`` module.

    ``file_storage.py`` does ``import aioboto3`` at module-load time
    and then calls ``aioboto3.Session()`` inside each S3 helper.
    Patching the symbol on the module rebinds those calls to our mock
    without ever touching the real boto3 client machinery. Yields the
    ``Session`` MagicMock so each test customises the client per-call.
    """
    session_factory = MagicMock()
    with patch.object(fs_module.aioboto3, "Session", session_factory):
        yield session_factory


def _enable_s3(
    monkeypatch: pytest.MonkeyPatch,
    *,
    aws_access_key_id: str = "",
    aws_secret_access_key: str = "",
    aws_session_token: str = "",
) -> FileStorage:
    # Tests construct the config directly rather than via env vars +
    # global ``settings`` — pydantic-settings caches the parse on first
    # access and would otherwise leak between tests.
    # ``model_construct`` skips Pydantic validation; safe here because
    # we're exercising ``FileStorage`` behaviour, not field coercion.
    return FileStorage(
        config=FileStorageConfig.model_construct(
            use_s3=True,
            s3_bucket="test-bucket",
            s3_region="us-east-1",
            local_dir="data/uploads",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
        )
    )


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


# ── Misconfig guard ─────────────────────────────────────────────────


def test_s3_enabled_without_bucket_raises_at_init() -> None:
    # Catching this at construction makes the misconfig a boot-time
    # log line, not an opaque boto3 ``ParamValidationError`` on the
    # first user-triggered upload.
    cfg = FileStorageConfig.model_construct(
        use_s3=True,
        s3_bucket="",
        s3_region="us-east-1",
        local_dir="data/uploads",
    )
    with pytest.raises(FileStorageError, match="FILE_STORAGE_S3_BUCKET is empty"):
        FileStorage(config=cfg)


def test_local_backend_without_bucket_initialises_normally() -> None:
    # The bucket guard must only fire when S3 is actually enabled.
    cfg = FileStorageConfig.model_construct(
        use_s3=False,
        s3_bucket="",
        s3_region="us-east-1",
        local_dir="data/uploads",
    )
    storage = FileStorage(config=cfg)
    assert storage.use_s3 is False


# ── End-to-end: .env → BaseSettings → FileStorage ───────────────────


def test_env_file_value_reaches_filestorage(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression guard for the bug that prompted this refactor:
    # ``.env`` with ``FILE_STORAGE_S3=true`` used to be ignored because
    # ``FileStorage`` called ``os.getenv`` directly while every other
    # config read through pydantic-settings. ``BaseSettings`` loads
    # ``env_file`` into the model but does NOT mutate ``os.environ``,
    # so the operator's env file was a no-op for storage selection.
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FILE_STORAGE_S3=true\n"
        "FILE_STORAGE_S3_BUCKET=evidence-from-envfile\n"
        "AWS_REGION=eu-west-2\n"
    )
    # Real ``FileStorageConfig`` construction targeting the temp .env.
    cfg = FileStorageConfig(_env_file=str(env_file))  # type: ignore[call-arg]

    assert cfg.use_s3 is True
    assert cfg.s3_bucket == "evidence-from-envfile"
    assert cfg.s3_region == "eu-west-2"

    storage = FileStorage(config=cfg)
    assert storage.use_s3 is True
    assert storage.s3_bucket == "evidence-from-envfile"
    assert storage.s3_region == "eu-west-2"


# ── Explicit AWS credential precedence ─────────────────────────────


async def test_explicit_aws_creds_passed_to_session(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    # When both ``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY`` are
    # present in the config, they MUST reach ``aioboto3.Session(...)``
    # explicitly — that's how boto3 picks ``.env`` creds over a stale
    # ``~/.aws/credentials`` file. The default chain (env → file →
    # role) only reads ``os.environ``, which pydantic-settings does
    # not populate.
    storage = _enable_s3(
        monkeypatch,
        aws_access_key_id="AKIA-from-env",
        aws_secret_access_key="secret-from-env",
    )
    fake_aioboto3.return_value = _s3_client_mock()
    await storage._upload_s3("org/qa-evidence/x.png", b"data", "image/png")
    fake_aioboto3.assert_called_once_with(
        aws_access_key_id="AKIA-from-env",
        aws_secret_access_key="secret-from-env",
    )


async def test_session_token_included_when_set(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    storage = _enable_s3(
        monkeypatch,
        aws_access_key_id="AKIA-temp",
        aws_secret_access_key="secret-temp",
        aws_session_token="sts-temporary-token",
    )
    fake_aioboto3.return_value = _s3_client_mock()
    await storage._upload_s3("org/qa-evidence/x.png", b"data", "image/png")
    fake_aioboto3.assert_called_once_with(
        aws_access_key_id="AKIA-temp",
        aws_secret_access_key="secret-temp",
        aws_session_token="sts-temporary-token",
    )


async def test_default_chain_used_when_no_explicit_creds(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    # Without explicit creds, ``aioboto3.Session()`` must be called
    # with no kwargs so boto3 falls through to its default chain
    # (``os.environ`` → ``~/.aws/credentials`` → IAM role).
    storage = _enable_s3(monkeypatch)
    fake_aioboto3.return_value = _s3_client_mock()
    await storage._upload_s3("org/qa-evidence/x.png", b"data", "image/png")
    fake_aioboto3.assert_called_once_with()


async def test_partial_creds_falls_back_to_default_chain(
    monkeypatch: pytest.MonkeyPatch, fake_aioboto3: MagicMock
) -> None:
    # Only the access key set without the secret (or vice versa) is
    # almost always a config typo. Treat it as "no explicit creds"
    # and route through the default chain rather than guessing.
    storage = _enable_s3(
        monkeypatch,
        aws_access_key_id="AKIA-orphan",
        aws_secret_access_key="",
    )
    fake_aioboto3.return_value = _s3_client_mock()
    await storage._upload_s3("org/qa-evidence/x.png", b"data", "image/png")
    fake_aioboto3.assert_called_once_with()
