# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Restore-side-effect invariants.

Pins the four behaviours that keep a restored BUD consistent with the
artefacts derived from its content:

1. The phase-progression gate refuses restores once the BUD has moved
   past the snapshot's phase — downstream artefacts (todos, PRs,
   estimates) reference the newer content and reverting the source
   would leave them dangling.
2. Restoring the BUD phase regenerates the embedding so the bug-linker
   stops matching against text that no longer exists.
3. Restoring the BUD phase re-parses the trailing linked-feature JSON
   fence so BUDFeatureLink rows match the restored requirements.
4. Restoring a non-BUD phase (e.g. TECH_ARCH) does NOT touch the
   embedding or feature links — those are derived from
   ``requirements_md`` only.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.bud import BUDStatus
from app.services import bud_version_restore


def _fake_bud(
    *,
    status: BUDStatus = BUDStatus.BUD,
    requirements_md: str | None = "current body",
    title: str = "Demo",
) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        status=status,
        title=title,
        requirements_md=requirements_md,
        tech_spec_md=None,
        test_plan_md=None,
        code_review_comments=None,
        qa_automation_cases=None,
        qa_manual_cases=None,
        qa_execution_plan_md=None,
        assignee_id=None,
        auto_generate_phases=None,
        metadata_=None,
        impacted_repos=None,
        embedding=None,
    )


def _fake_actor() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name="Ada", email="ada@example.com")


def _fake_target(
    *,
    phase: BUDStatus = BUDStatus.BUD,
    requirements_md: str | None = "old body",
) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        phase=phase,
        version_no=3,
        snapshot={
            "title": "Demo",
            "requirements_md": requirements_md,
        },
    )


def test_phase_gate_blocks_restoring_bud_after_tech_arch_started() -> None:
    """Once the BUD reaches TECH_ARCH, todos and impacted_repos are derived
    from the tech spec which was built off the BUD-phase content. Reverting
    requirements at that point would diverge the spec from its source."""
    bud = _fake_bud(status=BUDStatus.TECH_ARCH)
    with pytest.raises(HTTPException) as exc:
        bud_version_restore.assert_phase_allows_restore(bud, BUDStatus.BUD)
    assert exc.value.status_code == 409
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail["code"] == "phase_progressed"


def test_phase_gate_allows_same_phase_restore() -> None:
    """Restoring TECH_ARCH content while still in TECH_ARCH is the
    happy path — no downstream artefacts have been derived yet."""
    bud = _fake_bud(status=BUDStatus.TECH_ARCH)
    # Should not raise.
    bud_version_restore.assert_phase_allows_restore(bud, BUDStatus.TECH_ARCH)


def test_phase_gate_blocks_closed_bud() -> None:
    bud = _fake_bud(status=BUDStatus.CLOSED)
    with pytest.raises(HTTPException) as exc:
        bud_version_restore.assert_phase_allows_restore(bud, BUDStatus.BUD)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_requirements_restore_regenerates_embedding_and_reparses_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restoring the BUD phase MUST refresh both the embedding and the
    linked-feature rows — otherwise bug-linker and downstream agents
    consume stale derived state."""
    bud = _fake_bud(status=BUDStatus.BUD, requirements_md="new requirements text")
    actor = _fake_actor()
    target = _fake_target(phase=BUDStatus.BUD, requirements_md="old requirements text")
    db = MagicMock(flush=AsyncMock())

    embed_calls: list[str] = []
    feature_calls: list[dict[str, Any]] = []

    async def _embed(text: str) -> list[float]:
        embed_calls.append(text)
        return [0.1] * 384

    async def _persist(*, bud_id: Any, org_id: Any, content: str, **kw: Any) -> int:
        feature_calls.append({"bud_id": bud_id, "content": content, **kw})
        return 2

    async def _persist_positional(
        bud_id: Any, org_id: Any, content: str, db_: Any, **kw: Any
    ) -> int:
        # Real signature is positional; match it precisely.
        feature_calls.append({"bud_id": bud_id, "content": content, **kw})
        return 2

    async def _record(db_: Any, *args: Any, **kw: Any) -> Any:
        return MagicMock()

    async def _insert_snapshot(db_: Any, **kw: Any) -> Any:
        return MagicMock()

    monkeypatch.setattr(bud_version_restore.embedding_service, "embed", _embed)
    monkeypatch.setattr(
        bud_version_restore, "persist_linked_features_from_markdown", _persist_positional
    )
    monkeypatch.setattr(bud_version_restore, "record_event", _record)
    monkeypatch.setattr(bud_version_restore.bud_version_repo, "insert_snapshot", _insert_snapshot)

    result = await bud_version_restore.restore_bud_to_version(db, bud, target, actor)

    # Snapshot value landed on the BUD.
    assert bud.requirements_md == "old requirements text"
    # Embedding was regenerated from the restored content.
    assert len(embed_calls) == 1
    assert "old requirements text" in embed_calls[0]
    assert result["embedding_refreshed"] is True
    # Feature link reparse fired with the restored content.
    assert len(feature_calls) == 1
    assert feature_calls[0]["content"] == "old requirements text"
    assert result["linked_features_reparsed"] == 2


@pytest.mark.asyncio
async def test_restore_without_requirements_change_skips_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restoring a snapshot whose ``requirements_md`` matches the current
    value (e.g. user picked a tech_arch-phase snapshot) must NOT pay the
    embedding round-trip — that path is only relevant when requirements
    actually changed."""
    bud = _fake_bud(status=BUDStatus.TECH_ARCH, requirements_md="same text")
    actor = _fake_actor()
    target = _fake_target(phase=BUDStatus.TECH_ARCH, requirements_md=None)
    # The snapshot doesn't carry requirements_md at all (tech_arch
    # snapshots focus on tech_spec_md) — so the restore mustn't touch
    # the requirements column either.
    target.snapshot = {"tech_spec_md": "new spec"}
    bud.tech_spec_md = "old spec"
    db = MagicMock(flush=AsyncMock())

    embed_called = False

    async def _embed_should_not_be_called(text: str) -> list[float]:
        nonlocal embed_called
        embed_called = True
        return [0.0] * 384

    async def _record(db_: Any, *args: Any, **kw: Any) -> Any:
        return MagicMock()

    async def _insert_snapshot(db_: Any, **kw: Any) -> Any:
        return MagicMock()

    monkeypatch.setattr(
        bud_version_restore.embedding_service, "embed", _embed_should_not_be_called
    )
    monkeypatch.setattr(bud_version_restore, "record_event", _record)
    monkeypatch.setattr(bud_version_restore.bud_version_repo, "insert_snapshot", _insert_snapshot)

    result = await bud_version_restore.restore_bud_to_version(db, bud, target, actor)

    assert embed_called is False
    assert result["embedding_refreshed"] is False
    assert result["linked_features_reparsed"] == 0
    # The tech_spec column WAS restored.
    assert bud.tech_spec_md == "new spec"
