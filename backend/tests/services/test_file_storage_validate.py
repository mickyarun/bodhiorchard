# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""``FileStorage.validate_config`` startup-time checks.

Pre-fix failure mode: a misconfigured S3 backend ( ``FILE_STORAGE_S3=true``
but no bucket) deferred its error until the first user-triggered upload,
where it surfaced as a cryptic ``aioboto3`` traceback in logs the
operator had no reason to read. Local-disk-on-Docker had its own quiet
footgun — evidence vanished on every container rebuild because
``data/uploads`` resolves to ``/app/data/uploads`` inside the container
without a volume mount.

These tests pin the loud-fail / loud-warn behaviour the new
``validate_config`` is supposed to provide.
"""

from __future__ import annotations

import logging

import pytest

from app.services.file_storage import FileStorage, FileStorageError


def test_s3_enabled_without_bucket_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_S3", "true")
    monkeypatch.setenv("FILE_STORAGE_S3_BUCKET", "")
    storage = FileStorage()
    with pytest.raises(FileStorageError, match="FILE_STORAGE_S3_BUCKET"):
        storage.validate_config()


def test_s3_enabled_with_bucket_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_S3", "true")
    monkeypatch.setenv("FILE_STORAGE_S3_BUCKET", "my-evidence-bucket")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    storage = FileStorage()
    storage.validate_config()  # must not raise


def test_local_backend_validates_without_warning_when_path_looks_persistent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # ``tmp_path`` is under ``/var/folders`` / ``/tmp`` — outside the
    # ``/app`` container root, so the ephemeral-mount warning must NOT
    # fire. (Hybrid host mode points at host-owned paths like this.)
    monkeypatch.setenv("FILE_STORAGE_S3", "false")
    monkeypatch.setenv("FILE_STORAGE_LOCAL_DIR", str(tmp_path))
    storage = FileStorage()
    with caplog.at_level(logging.WARNING):
        storage.validate_config()
    # No "may be ephemeral" warning logged.
    assert not any(
        "file_storage_local_dir_may_be_ephemeral" in r.getMessage() for r in caplog.records
    )


def test_local_default_dir_resolves_via_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    # When ``FILE_STORAGE_LOCAL_DIR`` is left at its default
    # (``data/uploads``, a relative path), it should still validate
    # without raising — the warning logic is best-effort, never a hard
    # failure for a misshapen path. This guard catches a future refactor
    # that accidentally hard-fails on the default deploy config.
    monkeypatch.setenv("FILE_STORAGE_S3", "false")
    monkeypatch.delenv("FILE_STORAGE_LOCAL_DIR", raising=False)
    storage = FileStorage()
    storage.validate_config()  # must not raise
