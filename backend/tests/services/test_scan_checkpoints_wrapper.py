# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for ``run_checkpointed_phase``.

The dedicated checkpoint session helper (``_checkpoint_tx``) is
monkeypatched to yield an in-memory fake repository so the wrapper's
control flow is exercised without a live database. DB-level durability
coverage arrives in ``test_scan_checkpoints_durability.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.models.scan_phase import CheckpointStatus, ScanErrorCode, ScanPhase
from app.services import scan_checkpoints as sc


@dataclass
class _FakeCheckpoint:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    scan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    repo_id: uuid.UUID | None = None
    phase: ScanPhase = ScanPhase.MODE_DETECTION
    status: CheckpointStatus = CheckpointStatus.RUNNING
    attempt: int = 1
    payload: dict[str, Any] = field(default_factory=dict)
    sha_at_run: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class _FakeRepo:
    """Minimal stand-in for ``ScanPhaseCheckpointRepository``.

    Mirrors only the surface area used by ``run_checkpointed_phase``;
    any additional method call would raise ``AttributeError`` and surface
    a test-coverage gap.
    """

    rows: list[_FakeCheckpoint] = field(default_factory=list)
    cross_scan_reusable: _FakeCheckpoint | None = None

    async def get_latest(
        self,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        phase: ScanPhase,
    ) -> _FakeCheckpoint | None:
        matches = [
            r
            for r in self.rows
            if r.scan_id == scan_id and r.repo_id == repo_id and r.phase is phase
        ]
        return matches[-1] if matches else None

    async def find_sha_reusable(
        self,
        repo_id: uuid.UUID,
        phase: ScanPhase,
        sha: str,
    ) -> _FakeCheckpoint | None:
        src = self.cross_scan_reusable
        if src is None:
            return None
        if src.repo_id == repo_id and src.phase is phase and src.sha_at_run == sha:
            return src
        return None

    async def insert_reused(
        self,
        *,
        scan_id: uuid.UUID,
        parent_scan_id: uuid.UUID | None,
        repo_id: uuid.UUID | None,
        phase: ScanPhase,
        payload: dict[str, Any],
        sha_at_run: str | None,
    ) -> uuid.UUID:
        row = _FakeCheckpoint(
            scan_id=scan_id,
            repo_id=repo_id,
            phase=phase,
            status=CheckpointStatus.DONE,
            payload=payload,
            sha_at_run=sha_at_run,
        )
        self.rows.append(row)
        return row.id

    async def start(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        phase: ScanPhase,
        parent_scan_id: uuid.UUID | None = None,
        sha_at_run: str | None = None,
    ) -> uuid.UUID:
        row = _FakeCheckpoint(
            scan_id=scan_id,
            repo_id=repo_id,
            phase=phase,
            status=CheckpointStatus.RUNNING,
            sha_at_run=sha_at_run,
        )
        self.rows.append(row)
        return row.id

    async def finalize_by_id(
        self,
        checkpoint_id: uuid.UUID,
        *,
        status: CheckpointStatus,
        payload: dict[str, Any] | None = None,
        sha_at_run: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        for row in self.rows:
            if row.id == checkpoint_id:
                row.status = status
                if payload is not None:
                    row.payload = payload
                if sha_at_run is not None:
                    row.sha_at_run = sha_at_run
                row.error_code = error_code
                row.error_message = error_message
                return
        raise AssertionError(f"finalize_by_id: no checkpoint with id={checkpoint_id}")


@pytest.fixture
def _fake_repo(monkeypatch: pytest.MonkeyPatch) -> _FakeRepo:
    """Replace the dedicated checkpoint session helper with an in-memory fake.

    ``run_checkpointed_phase`` enters every read/write through
    ``_checkpoint_tx`` — patching that symbol short-circuits the real
    ``AsyncSessionLocal`` so wrapper tests stay pure unit tests. If the
    wrapper ever changes how it acquires the repo, update this fixture
    in lockstep — otherwise the helper silently opens a real Postgres
    connection.
    """
    fake = _FakeRepo()

    @asynccontextmanager
    async def fake_tx(_org_id: uuid.UUID) -> AsyncIterator[_FakeRepo]:
        yield fake

    monkeypatch.setattr(sc, "_checkpoint_tx", fake_tx)
    return fake


async def test_run_skips_when_already_done(_fake_repo: _FakeRepo) -> None:
    """DONE checkpoint in this scan → wrapper returns cached payload, skips body."""
    scan_id, org_id, repo_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _fake_repo.rows.append(
        _FakeCheckpoint(
            scan_id=scan_id,
            repo_id=repo_id,
            phase=ScanPhase.GITNEXUS_INDEX,
            status=CheckpointStatus.DONE,
            payload={"clusters": ["auth", "billing"]},
        )
    )
    body_called = False

    async def phase_fn() -> dict[str, Any]:
        nonlocal body_called
        body_called = True
        return {}

    outcome = await sc.run_checkpointed_phase(
        db=None,  # type: ignore[arg-type] - fake repo ignores db
        scan_id=scan_id,
        org_id=org_id,
        phase=ScanPhase.GITNEXUS_INDEX,
        phase_fn=phase_fn,
        repo_id=repo_id,
    )
    assert body_called is False
    assert outcome.was_skipped is True
    assert outcome.was_reused is False
    assert outcome.payload == {"clusters": ["auth", "billing"]}


async def test_run_reuses_across_scans_on_sha_match(_fake_repo: _FakeRepo) -> None:
    """Prior DONE checkpoint with same SHA → wrapper copies payload, skips body.

    Uses ``SKILL_EXTRACTION`` because ``GITNEXUS_INDEX`` is no longer
    in ``SHA_REUSABLE_PHASES`` (it has a closure side-channel that
    cross-scan reuse silently breaks — see scan_phase.py docstring).
    """
    scan_id, org_id, repo_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sha = "a" * 40
    _fake_repo.cross_scan_reusable = _FakeCheckpoint(
        scan_id=uuid.uuid4(),
        repo_id=repo_id,
        phase=ScanPhase.SKILL_EXTRACTION,
        status=CheckpointStatus.DONE,
        payload={"clusters": ["cached"]},
        sha_at_run=sha,
    )

    body_called = False

    async def phase_fn() -> dict[str, Any]:
        nonlocal body_called
        body_called = True
        return {}

    outcome = await sc.run_checkpointed_phase(
        db=None,  # type: ignore[arg-type]
        scan_id=scan_id,
        org_id=org_id,
        phase=ScanPhase.SKILL_EXTRACTION,
        phase_fn=phase_fn,
        repo_id=repo_id,
        sha=sha,
    )
    assert body_called is False
    assert outcome.was_reused is True
    assert outcome.payload == {"clusters": ["cached"]}


async def test_run_does_not_reuse_for_non_reusable_phase(
    _fake_repo: _FakeRepo,
) -> None:
    """FEATURE_SYNTHESIS is not in SHA_REUSABLE_PHASES → always runs body."""
    scan_id, org_id, repo_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _fake_repo.cross_scan_reusable = _FakeCheckpoint(
        scan_id=uuid.uuid4(),
        repo_id=repo_id,
        phase=ScanPhase.FEATURE_SYNTHESIS,
        status=CheckpointStatus.DONE,
        payload={"features": 1},
        sha_at_run="abc",
    )
    body_called = False

    async def phase_fn() -> dict[str, Any]:
        nonlocal body_called
        body_called = True
        return {"features": 2}

    outcome = await sc.run_checkpointed_phase(
        db=None,  # type: ignore[arg-type]
        scan_id=scan_id,
        org_id=org_id,
        phase=ScanPhase.FEATURE_SYNTHESIS,
        phase_fn=phase_fn,
        repo_id=repo_id,
        sha="abc",
    )
    assert body_called is True
    assert outcome.was_reused is False
    assert outcome.payload == {"features": 2}


async def test_run_success_writes_done_checkpoint(_fake_repo: _FakeRepo) -> None:
    """Happy path → RUNNING then DONE with the returned payload."""
    scan_id, org_id, repo_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def phase_fn() -> dict[str, Any]:
        return {"stale_cleaned": 3}

    outcome = await sc.run_checkpointed_phase(
        db=None,  # type: ignore[arg-type]
        scan_id=scan_id,
        org_id=org_id,
        phase=ScanPhase.STALE_CLEANUP,
        phase_fn=phase_fn,
        repo_id=repo_id,
    )
    assert outcome.payload == {"stale_cleaned": 3}
    assert outcome.was_skipped is False
    assert outcome.was_reused is False
    assert len(_fake_repo.rows) == 1
    assert _fake_repo.rows[0].status is CheckpointStatus.DONE


async def test_run_failure_records_classified_error_and_reraises(
    _fake_repo: _FakeRepo,
) -> None:
    """Failure path → FAILED checkpoint with error_code set, exception re-raised."""
    scan_id, org_id, repo_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def phase_fn() -> dict[str, Any]:
        raise sc.MaxTurnsError("num_turns=41 max_turns=40")

    with pytest.raises(sc.MaxTurnsError):
        await sc.run_checkpointed_phase(
            db=None,  # type: ignore[arg-type]
            scan_id=scan_id,
            org_id=org_id,
            phase=ScanPhase.FEATURE_SYNTHESIS,
            phase_fn=phase_fn,
            repo_id=repo_id,
        )
    assert len(_fake_repo.rows) == 1
    row = _fake_repo.rows[0]
    assert row.status is CheckpointStatus.FAILED
    assert row.error_code == ScanErrorCode.MAX_TURNS.value
    assert "num_turns=41" in (row.error_message or "")


async def test_run_invokes_transition_hook_on_every_write(
    _fake_repo: _FakeRepo,
) -> None:
    """on_transition fires at RUNNING start and at DONE finalize — two times
    for a successful run. This is what drives the WS publish cadence."""
    scan_id, org_id = uuid.uuid4(), uuid.uuid4()
    calls: list[int] = []

    async def hook() -> None:
        calls.append(len(_fake_repo.rows))

    async def phase_fn() -> dict[str, Any]:
        return {}

    await sc.run_checkpointed_phase(
        db=None,  # type: ignore[arg-type]
        scan_id=scan_id,
        org_id=org_id,
        phase=ScanPhase.PERSIST_RESULTS,
        phase_fn=phase_fn,
        on_transition=hook,
    )
    # Two invocations: once after RUNNING insert, once after DONE finalize.
    assert len(calls) == 2


async def test_failure_path_uses_separate_checkpoint_tx_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the production durability bug.

    Production scenario (scan ``5fc39c5c-…``): ``feature_merge`` body
    raised ``MergeIncompleteError``; the checkpoint stayed RUNNING
    because the FAILED ``UPDATE`` was flushed into the same session as
    the phase body and rolled back together with it.

    The fix is structural: ``run_checkpointed_phase`` enters
    ``_checkpoint_tx`` *separately* for the start, the FAILED finalize,
    and the DONE finalize — every write commits in its own session. The
    test counts how many distinct ``_checkpoint_tx`` contexts the
    failure path opens. Two means start + finalize, which is what the
    fix delivers; one would mean the writes share a transaction (the
    bug) and zero would mean we never reached either branch.
    """
    fake = _FakeRepo()
    enter_count = 0

    @asynccontextmanager
    async def counting_tx(_org_id: uuid.UUID) -> AsyncIterator[_FakeRepo]:
        nonlocal enter_count
        enter_count += 1
        yield fake

    monkeypatch.setattr(sc, "_checkpoint_tx", counting_tx)

    async def phase_fn() -> dict[str, Any]:
        raise sc.MergeIncompleteError("9 unvisited features")

    with pytest.raises(sc.MergeIncompleteError):
        await sc.run_checkpointed_phase(
            db=None,  # type: ignore[arg-type]
            scan_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            phase=ScanPhase.FEATURE_MERGE,
            phase_fn=phase_fn,
        )

    # 1. start (RUNNING insert), 2. FAILED finalize. The skip-if-done
    # lookup short-circuits because no prior row exists for this scan
    # — confirmed by the row count below.
    assert enter_count == 3, (
        f"Expected 3 _checkpoint_tx contexts (skip lookup, start, FAILED finalize); "
        f"got {enter_count}. Fewer means writes are sharing a transaction."
    )
    assert len(fake.rows) == 1
    assert fake.rows[0].status is CheckpointStatus.FAILED
    assert fake.rows[0].error_code == ScanErrorCode.MERGE_INCOMPLETE.value
