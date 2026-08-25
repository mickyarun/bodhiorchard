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

"""Handler-level contract for ``POST /buds/{id}/restore``.

The orchestration itself is unit-tested in
``tests/services/test_bud_restore.py``; this file pins the HTTP edge:
which BUDs the endpoint refuses, that a refusal never mutates, that the
lookup is org-scoped and row-locked, and that the response goes through
the shared enricher rather than the raw ORM row.

Follows the directory convention (see ``conftest.py``): handler
functions are invoked directly with mocked sessions and repos — no DB,
no live ASGI server.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import bud_workflows
from app.models.bud import BUDStatus


def _make_bud(status: BUDStatus) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        bud_number=7,
        title="Retry logic",
        status=status,
    )


def _patch_repo(
    monkeypatch: pytest.MonkeyPatch,
    bud: SimpleNamespace | None,
    *,
    refreshed: SimpleNamespace | None = None,
) -> MagicMock:
    """Stub BUDRepository; returns the constructor mock for scope assertions."""
    repo = MagicMock(
        get_by_id_for_update=AsyncMock(return_value=bud),
        get_by_id=AsyncMock(return_value=refreshed if refreshed is not None else bud),
    )
    ctor = MagicMock(return_value=repo)
    monkeypatch.setattr(bud_workflows, "BUDRepository", ctor)
    return ctor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [BUDStatus.CLOSED, BUDStatus.DEVELOPMENT, BUDStatus.BUD],
)
async def test_non_discarded_bud_is_refused_without_mutating(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
    status: BUDStatus,
) -> None:
    """Only ``discarded`` restores.

    ``closed`` is the load-bearing case: closing already ran
    ``on_bud_closed`` (XP, SP, learning metrics, learning agent), so
    reopening one would let all of it fire again on the next close.
    """
    bud = _make_bud(status)
    _patch_repo(monkeypatch, bud)
    restore = AsyncMock()
    monkeypatch.setattr(bud_workflows, "restore_discarded_bud", restore)

    with pytest.raises(HTTPException) as excinfo:
        await bud_workflows.restore_bud(bud_id=bud.id, current_user=fake_user, db=fake_db)

    assert excinfo.value.status_code == 409
    assert status.value in str(excinfo.value.detail)
    # A refused request must not have touched anything.
    restore.assert_not_awaited()
    assert bud.status == status
    fake_db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_or_other_org_bud_is_404(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """A BUD belonging to another org is indistinguishable from a missing one.

    ``BUDRepository`` is constructed with the caller's ``org_id`` and
    scopes every query by it, so a cross-tenant id resolves to ``None``
    here — this asserts the scoping is actually wired, not just that the
    404 fires.
    """
    ctor = _patch_repo(monkeypatch, None)
    monkeypatch.setattr(bud_workflows, "restore_discarded_bud", AsyncMock())

    with pytest.raises(HTTPException) as excinfo:
        await bud_workflows.restore_bud(bud_id=uuid.uuid4(), current_user=fake_user, db=fake_db)

    assert excinfo.value.status_code == 404
    ctor.assert_called_once_with(fake_db, org_id=fake_user.org_id)


@pytest.mark.asyncio
async def test_discarded_bud_restores_under_a_row_lock_and_returns_enriched_payload(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """Happy path: locked read, delegated restore, enriched response.

    The read must go through ``get_by_id_for_update`` — without the lock
    two concurrent restores both clear the ``discarded`` guard and each
    append a timeline event. The response must go through
    ``build_bud_response``: returning the raw ORM row would ship designs
    with a null ``repo_name`` (the field has no ORM backing) into the
    page the user is looking at.
    """
    bud = _make_bud(BUDStatus.DISCARDED)
    refreshed = _make_bud(BUDStatus.TESTING)
    repo_ctor = _patch_repo(monkeypatch, bud, refreshed=refreshed)
    restore = AsyncMock(return_value=BUDStatus.TESTING)
    monkeypatch.setattr(bud_workflows, "restore_discarded_bud", restore)
    enriched = MagicMock(name="BUDRead")
    build = AsyncMock(return_value=enriched)
    monkeypatch.setattr(bud_workflows, "build_bud_response", build)

    result = await bud_workflows.restore_bud(bud_id=bud.id, current_user=fake_user, db=fake_db)

    repo = repo_ctor.return_value
    repo.get_by_id_for_update.assert_awaited_once_with(bud.id)
    restore.assert_awaited_once_with(fake_db, bud, fake_user)
    build.assert_awaited_once_with(refreshed, fake_user.org_id, fake_db)
    assert result is enriched


@pytest.mark.asyncio
async def test_bud_vanishing_between_restore_and_refetch_is_a_500_not_a_none_body(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """The post-restore refetch is guarded, so the route can't return null."""
    bud = _make_bud(BUDStatus.DISCARDED)
    repo = MagicMock(
        get_by_id_for_update=AsyncMock(return_value=bud),
        get_by_id=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(bud_workflows, "BUDRepository", MagicMock(return_value=repo))
    monkeypatch.setattr(bud_workflows, "restore_discarded_bud", AsyncMock())

    with pytest.raises(HTTPException) as excinfo:
        await bud_workflows.restore_bud(bud_id=bud.id, current_user=fake_user, db=fake_db)

    assert excinfo.value.status_code == 500


def test_restore_route_is_mounted_and_permission_gated() -> None:
    """``/restore`` exists on the workflows router with a dependency gate.

    The ``Depends(require_permissions("buds:edit"))`` chain never runs in
    these direct-handler tests, so this is the only place that notices if
    the gate is dropped from the decorator.
    """
    routes = [r for r in bud_workflows.router.routes if getattr(r, "path", "") == "/restore"]
    assert len(routes) == 1
    route = routes[0]
    assert route.methods == {"POST"}  # type: ignore[attr-defined]
    assert route.dependencies  # type: ignore[attr-defined]
