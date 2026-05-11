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

"""Unit tests for :mod:`app.services.scan_kickoff`."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services import scan_kickoff


@pytest.mark.asyncio
async def test_empty_repo_ids_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty repo_ids must short-circuit before any embedding/scan call."""
    embed_called = False
    scan_called = False

    async def _fake_check() -> tuple[bool, str]:
        nonlocal embed_called
        embed_called = True
        return True, ""

    async def _fake_scan(**_: Any) -> uuid.UUID:
        nonlocal scan_called
        scan_called = True
        return uuid.uuid4()

    monkeypatch.setattr(scan_kickoff.embedding_service, "check", _fake_check)
    monkeypatch.setattr(scan_kickoff, "start_scan", _fake_scan)

    scan_id, warning = await scan_kickoff.kick_off_onboard_scan(org_id=uuid.uuid4(), repo_ids=[])

    assert scan_id is None
    assert warning is None
    assert not embed_called
    assert not scan_called


@pytest.mark.asyncio
async def test_embedding_down_returns_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """When embedding_service.check fails, the helper warns and skips the scan."""
    scan_called = False

    async def _fake_check() -> tuple[bool, str]:
        return False, "connection refused"

    async def _fake_scan(**_: Any) -> uuid.UUID:
        nonlocal scan_called
        scan_called = True
        return uuid.uuid4()

    monkeypatch.setattr(scan_kickoff.embedding_service, "check", _fake_check)
    monkeypatch.setattr(scan_kickoff, "start_scan", _fake_scan)

    scan_id, warning = await scan_kickoff.kick_off_onboard_scan(
        org_id=uuid.uuid4(), repo_ids=[uuid.uuid4()]
    )

    assert scan_id is None
    assert warning is not None
    assert "connection refused" in warning
    assert not scan_called


@pytest.mark.asyncio
async def test_happy_path_returns_scan_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedding OK + non-empty repo_ids → scan_id, no warning."""
    expected_scan = uuid.uuid4()
    org_id = uuid.uuid4()
    repo_ids = [uuid.uuid4(), uuid.uuid4()]
    received_kwargs: dict[str, Any] = {}

    async def _fake_check() -> tuple[bool, str]:
        return True, ""

    async def _fake_scan(**kwargs: Any) -> uuid.UUID:
        received_kwargs.update(kwargs)
        return expected_scan

    monkeypatch.setattr(scan_kickoff.embedding_service, "check", _fake_check)
    monkeypatch.setattr(scan_kickoff, "start_scan", _fake_scan)

    scan_id, warning = await scan_kickoff.kick_off_onboard_scan(org_id=org_id, repo_ids=repo_ids)

    assert scan_id == expected_scan
    assert warning is None
    assert received_kwargs["org_id"] == org_id
    assert received_kwargs["repo_ids"] == repo_ids
    # No full_rescan override — runner's per-repo SHA gate handles it.
    assert received_kwargs["config"].full_rescan is False
