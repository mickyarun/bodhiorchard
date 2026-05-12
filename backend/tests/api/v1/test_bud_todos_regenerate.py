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

"""Tests for ``POST /buds/{id}/todos/regenerate``.

The repo has no HTTP+DB integration harness (see
``tests/api/v1/test_github_install_webhook.py``'s prelude); we invoke
the endpoint coroutine directly with stubbed collaborators.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import bud_todos as endpoint_module
from app.api.v1.bud_todos import regenerate_todos
from app.models.bud import BUDStatus


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def current_user(org_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), org_id=org_id, name="Alice")


def _patch_bud_repo(monkeypatch: pytest.MonkeyPatch, bud: object | None) -> None:
    """Stub BUDRepository(...).get_by_id to return ``bud``."""
    fake_repo = MagicMock(name="BUDRepository")
    fake_repo.get_by_id = AsyncMock(return_value=bud)
    monkeypatch.setattr(
        endpoint_module,
        "BUDRepository",
        MagicMock(return_value=fake_repo),
    )


def _capture_create_job(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``create_job`` with a recorder returning a fake JobStatusRead."""
    spy = MagicMock(name="create_job")
    spy.return_value = SimpleNamespace(job_id="job-123")
    monkeypatch.setattr(endpoint_module, "create_job", spy)
    return spy


def _patch_active(monkeypatch: pytest.MonkeyPatch, active: bool) -> None:
    """Stub ``is_job_active`` to return ``active``."""
    monkeypatch.setattr(endpoint_module, "is_job_active", MagicMock(return_value=active))


# ── happy path ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regenerate_enqueues_job_when_bud_in_development(
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
    org_id: uuid.UUID,
) -> None:
    bud_id = uuid.uuid4()
    bud = SimpleNamespace(id=bud_id, status=BUDStatus.DEVELOPMENT.value)
    _patch_bud_repo(monkeypatch, bud)
    _patch_active(monkeypatch, False)
    create_job_spy = _capture_create_job(monkeypatch)
    publish_spy = MagicMock()
    monkeypatch.setattr(endpoint_module, "publish", publish_spy)

    body = await regenerate_todos(bud_id, db=MagicMock(), current_user=current_user)  # type: ignore[arg-type]

    create_job_spy.assert_called_once()
    call_kwargs = create_job_spy.call_args.kwargs
    assert call_kwargs["payload"]["bud_id"] == str(bud_id)
    assert call_kwargs["payload"]["mode"] == "regenerate"
    assert call_kwargs["payload"]["org_id"] == str(org_id)
    publish_spy.assert_called_once_with(
        f"todo:{bud_id}",
        {"event": "regenerate_scheduled", "job_id": "job-123"},
    )
    assert body == {
        "topic": f"todo:{bud_id}",
        "job_id": "job-123",
        "status": "scheduled",
    }


# ── failure modes ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regenerate_409_when_job_already_active(
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    bud = SimpleNamespace(id=uuid.uuid4(), status=BUDStatus.DEVELOPMENT.value)
    _patch_bud_repo(monkeypatch, bud)
    _patch_active(monkeypatch, True)
    create_job_spy = _capture_create_job(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await regenerate_todos(
            uuid.uuid4(),
            db=MagicMock(),
            current_user=current_user,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409
    create_job_spy.assert_not_called()


@pytest.mark.asyncio
async def test_regenerate_404s_when_bud_missing(
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    _patch_bud_repo(monkeypatch, None)
    _patch_active(monkeypatch, False)
    create_job_spy = _capture_create_job(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await regenerate_todos(
            uuid.uuid4(),
            db=MagicMock(),
            current_user=current_user,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404
    create_job_spy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase",
    [BUDStatus.BUD.value, BUDStatus.DESIGN.value, BUDStatus.UAT.value],
)
async def test_regenerate_rejects_buds_not_in_development(
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
    phase: str,
) -> None:
    bud = SimpleNamespace(id=uuid.uuid4(), status=phase)
    _patch_bud_repo(monkeypatch, bud)
    _patch_active(monkeypatch, False)
    create_job_spy = _capture_create_job(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await regenerate_todos(
            uuid.uuid4(),
            db=MagicMock(),
            current_user=current_user,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 400
    assert phase in str(exc.value.detail)
    create_job_spy.assert_not_called()
