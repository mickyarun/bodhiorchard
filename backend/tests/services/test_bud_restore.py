# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Restore-a-discarded-BUD invariants.

Pins the behaviours that make un-discarding safe:

1. A restored BUD lands back on the phase it was discarded FROM, so a
   BUD binned during testing does not restart the pipeline.
2. Phases the org has since disabled (UAT off) and terminal phases fall
   back to ``bud`` — restoring into a column the board never renders
   would make the BUD invisible in the UI while present in the API.
3. Restore revives the feature that discard deactivated.
4. The restore is recorded as a normal ``status_change`` event tagged
   ``restored`` so existing timeline consumers pick it up unchanged.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bud import BUDStatus
from app.services import bud_restore


def _fake_bud(*, bud_number: int = 7) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        bud_number=bud_number,
        status=BUDStatus.DISCARDED,
    )


def _fake_actor() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), name="Ada")


def _patch_deps(
    monkeypatch: pytest.MonkeyPatch,
    *,
    previous: str | None,
    uat_enabled: bool = True,
) -> dict[str, list[Any]]:
    """Stub the timeline lookup + org config; capture feature/timeline writes."""
    calls: dict[str, list[Any]] = {"features": [], "events": []}

    timeline_repo = MagicMock(latest_status_change_from=AsyncMock(return_value=previous))
    monkeypatch.setattr(bud_restore, "BUDTimelineRepository", lambda db, *, org_id: timeline_repo)

    org = SimpleNamespace(config={"bud_stages": {"uat_enabled": uat_enabled}})
    monkeypatch.setattr(
        bud_restore,
        "OrganizationRepository",
        lambda db: MagicMock(get_by_id=AsyncMock(return_value=org)),
    )

    async def _restore_feature(db: Any, org_id: Any, bud_number: int) -> None:
        calls["features"].append(bud_number)

    async def _record(db: Any, org_id: Any, bud_id: Any, event_type: str, **kw: Any) -> Any:
        calls["events"].append({"type": event_type, **kw})
        return MagicMock()

    monkeypatch.setattr(bud_restore, "restore_feature_for_bud", _restore_feature)
    monkeypatch.setattr(bud_restore, "record_event", _record)
    return calls


@pytest.mark.asyncio
async def test_resolves_to_phase_bud_was_discarded_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A BUD binned during testing comes back in testing."""
    _patch_deps(monkeypatch, previous="testing")
    bud = _fake_bud()

    result = await bud_restore.resolve_restore_status(MagicMock(), uuid.uuid4(), bud)

    assert result is BUDStatus.TESTING


@pytest.mark.asyncio
async def test_resolves_to_first_phase_when_no_discard_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUDs discarded by an importer (or before timeline events existed)
    have no recorded ``from`` phase — restart rather than guess."""
    _patch_deps(monkeypatch, previous=None)
    bud = _fake_bud()

    result = await bud_restore.resolve_restore_status(MagicMock(), uuid.uuid4(), bud)

    assert result is bud_restore.RESTORE_FALLBACK_STATUS


@pytest.mark.asyncio
async def test_disabled_phase_falls_back_to_first_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restoring into UAT after the org turned UAT off would drop the BUD
    into a column the board never renders."""
    _patch_deps(monkeypatch, previous="uat", uat_enabled=False)
    bud = _fake_bud()

    result = await bud_restore.resolve_restore_status(MagicMock(), uuid.uuid4(), bud)

    assert result is bud_restore.RESTORE_FALLBACK_STATUS


@pytest.mark.asyncio
async def test_terminal_previous_phase_falls_back_to_first_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A BUD closed and then discarded must not resurrect as closed —
    ``closed`` is not a pipeline phase, so the phase-order filter rejects it."""
    _patch_deps(monkeypatch, previous="closed")
    bud = _fake_bud()

    result = await bud_restore.resolve_restore_status(MagicMock(), uuid.uuid4(), bud)

    assert result is bud_restore.RESTORE_FALLBACK_STATUS


@pytest.mark.asyncio
async def test_restore_sets_status_revives_feature_and_records_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_deps(monkeypatch, previous="development")
    bud = _fake_bud(bud_number=42)
    actor = _fake_actor()
    db = MagicMock(flush=AsyncMock(), refresh=AsyncMock())

    target = await bud_restore.restore_discarded_bud(db, bud, actor)

    assert target is BUDStatus.DEVELOPMENT
    assert bud.status is BUDStatus.DEVELOPMENT
    # The feature deactivated on discard is revived, keyed by BUD number.
    assert calls["features"] == [42]
    # Recorded as a plain status_change so existing consumers see it.
    assert len(calls["events"]) == 1
    event = calls["events"][0]
    assert event["type"] == "status_change"
    assert event["detail"] == {
        "from": "discarded",
        "to": "development",
        "restored": True,
    }
    assert event["actor_id"] == actor.id
