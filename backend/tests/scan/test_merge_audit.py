# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Strict post-merge audit tests.

Under the staging-then-merge model, ``phase_b3_merge`` is the sole
writer of canonical ``knowledge_items``. Every NEW synth row produced
in a scan must end the merge with a non-NULL ``merge_outcome`` AND a
non-NULL ``knowledge_item_id``. Anything else is a logic bug —
``_audit_strict`` raises ``MergeIncompleteError`` so the FEATURE_MERGE
checkpoint lands FAILED with ``error_code='merge_incomplete'``.

The two-tier "active-KI fallback" from the legacy flow is gone: there
is no longer a path where a synth row can be CANONICAL without us
having created its canonical KI ourselves.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


class _StubSynthRow:
    """Bare-minimum stand-in for ``SynthesizedFeature`` at the audit boundary."""

    def __init__(self, sid: uuid.UUID) -> None:
        self.id = sid


class _StubSynthRepo:
    """Stub for ``SynthesizedFeatureRepository`` exposing only the audit seam."""

    def __init__(self, leftover_ids: list[uuid.UUID]) -> None:
        self._leftover = [_StubSynthRow(sid) for sid in leftover_ids]
        self.calls: list[str] = []

    async def list_unmerged_for_scan(self, scan_id: uuid.UUID) -> list[_StubSynthRow]:
        self.calls.append(f"list_unmerged:{scan_id}")
        return list(self._leftover)


async def _run_audit_with_stub(stub: _StubSynthRepo) -> None:
    """Invoke the audit body, swapping in the stub repository.

    ``_audit_strict`` constructs its own ``SynthesizedFeatureRepository``
    instance internally; we monkey-patch the constructor for the
    duration of the call so the test stays focused on the audit rule
    instead of the repository wiring.
    """
    from app.services.scan.phase_impls import feature_merge

    class _Factory:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        async def list_unmerged_for_scan(self, scan_id: uuid.UUID) -> list[_StubSynthRow]:
            return await stub.list_unmerged_for_scan(scan_id)

    original = feature_merge.SynthesizedFeatureRepository
    feature_merge.SynthesizedFeatureRepository = _Factory  # type: ignore[assignment,misc]
    try:
        await feature_merge._audit_strict(
            db=None,  # type: ignore[arg-type]
            org_id=uuid.uuid4(),
            scan_uuid=uuid.uuid4(),
        )
    finally:
        feature_merge.SynthesizedFeatureRepository = original  # type: ignore[assignment,misc]


@pytest.mark.asyncio(loop_scope="function")
async def test_audit_passes_when_no_leftover_rows() -> None:
    """The healthy case: every NEW synth row got an outcome."""
    stub = _StubSynthRepo(leftover_ids=[])
    # Should NOT raise.
    await _run_audit_with_stub(stub)
    assert any(call.startswith("list_unmerged:") for call in stub.calls)


@pytest.mark.asyncio(loop_scope="function")
async def test_audit_raises_when_leftover_rows_remain() -> None:
    """A single unstamped synth row fails the whole merge phase."""
    from app.services.scan_checkpoints import MergeIncompleteError

    leftover = [uuid.uuid4()]
    stub = _StubSynthRepo(leftover_ids=leftover)

    with pytest.raises(MergeIncompleteError) as exc_info:
        await _run_audit_with_stub(stub)

    assert "1 synth row" in str(exc_info.value)
    assert str(leftover[0]) in str(exc_info.value)


@pytest.mark.asyncio(loop_scope="function")
async def test_audit_truncates_long_leftover_lists() -> None:
    """The error message caps the id list so logs stay readable."""
    from app.services.scan_checkpoints import MergeIncompleteError

    many = [uuid.uuid4() for _ in range(15)]
    stub = _StubSynthRepo(leftover_ids=many)

    with pytest.raises(MergeIncompleteError) as exc_info:
        await _run_audit_with_stub(stub)

    msg = str(exc_info.value)
    assert "15 synth row" in msg
    # Truncation marker present once the count exceeds 10.
    assert "…" in msg
