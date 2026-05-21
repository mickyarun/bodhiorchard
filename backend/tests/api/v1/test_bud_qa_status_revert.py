# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""``PATCH /qa/manual-results`` accepts ``pending`` to revert a mark.

A QA tester needs to be able to un-mark a previous Pass/Fail decision
when a regression invalidates the earlier judgement — re-running the
case against a fixed build, replaying after an env mishap, etc. The
schema now accepts ``pending`` and the handler erases the prior
tester / timestamp / notes so the case looks genuinely untested again
(otherwise stale attribution would imply the new pending state was the
original tester's call).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import bud_qa as qa_handlers
from app.schemas.qa import ManualTestResultUpdate


def _make_bud_with_case(case_data: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        qa_manual_cases=[case_data],
    )


def _patch_bud_repo(monkeypatch: pytest.MonkeyPatch, bud: SimpleNamespace | None) -> None:
    repo = MagicMock(get_by_id_for_update=AsyncMock(return_value=bud))
    monkeypatch.setattr(qa_handlers, "BUDRepository", MagicMock(return_value=repo))
    # ``flag_modified`` is a SQLAlchemy ORM hint that expects a real
    # mapped instance — our SimpleNamespace stand-in doesn't have
    # ``_sa_instance_state``. The handler's call site is just nudging
    # the JSONB column, so a no-op patch is faithful at this level.
    monkeypatch.setattr(qa_handlers, "flag_modified", lambda *a, **kw: None)


@pytest.mark.asyncio
async def test_pending_revert_clears_tester_and_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    # Original "pass" mark stored by a previous tester.
    case = {
        "id": "MTC-001",
        "result": "pass",
        "tester_name": "Original Tester",
        "tested_at": "2026-05-19T08:00:00+00:00",
        "notes": "Looked good then",
    }
    bud = _make_bud_with_case(case)
    _patch_bud_repo(monkeypatch, bud)

    fake_db.commit = AsyncMock()
    await qa_handlers.update_manual_result(
        bud_id=bud.id,
        body=ManualTestResultUpdate(test_case_id="MTC-001", result="pending"),
        db=fake_db,
        current_user=fake_user,
    )

    updated = bud.qa_manual_cases[0]
    assert updated["result"] == "pending"
    assert updated["tester_name"] is None
    assert updated["tested_at"] is None
    # Stale "looked good then" note from the prior Pass must not
    # outlive the Pass — implies the new pending state agreed with it.
    assert updated["notes"] is None


@pytest.mark.asyncio
async def test_pending_revert_keeps_explicit_new_notes(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    case = {
        "id": "MTC-002",
        "result": "fail",
        "tester_name": "Other",
        "tested_at": "2026-05-19T08:00:00+00:00",
        "notes": "Old failure note",
    }
    bud = _make_bud_with_case(case)
    _patch_bud_repo(monkeypatch, bud)
    fake_db.commit = AsyncMock()

    await qa_handlers.update_manual_result(
        bud_id=bud.id,
        body=ManualTestResultUpdate(
            test_case_id="MTC-002",
            result="pending",
            notes="Re-testing after fix",
        ),
        db=fake_db,
        current_user=fake_user,
    )

    updated = bud.qa_manual_cases[0]
    assert updated["result"] == "pending"
    # Caller supplied a fresh note explaining the revert — preserve it.
    assert updated["notes"] == "Re-testing after fix"
    assert updated["tester_name"] is None
    assert updated["tested_at"] is None


@pytest.mark.asyncio
async def test_non_pending_results_still_attribute_tester(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    # Regression guard: the new pending branch must not have leaked
    # into the pass/fail/blocked/skipped path. Each non-pending result
    # still stamps the current user + now() for audit attribution.
    case = {"id": "MTC-003", "result": "pending", "tester_name": None}
    bud = _make_bud_with_case(case)
    _patch_bud_repo(monkeypatch, bud)
    fake_db.commit = AsyncMock()
    fake_user.name = "Daisy"

    await qa_handlers.update_manual_result(
        bud_id=bud.id,
        body=ManualTestResultUpdate(test_case_id="MTC-003", result="pass"),
        db=fake_db,
        current_user=fake_user,
    )

    updated = bud.qa_manual_cases[0]
    assert updated["result"] == "pass"
    assert updated["tester_name"] == "Daisy"
    assert updated["tested_at"] is not None  # ISO timestamp set


@pytest.mark.asyncio
async def test_missing_case_id_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    bud = _make_bud_with_case({"id": "MTC-001", "result": "pass"})
    _patch_bud_repo(monkeypatch, bud)
    fake_db.commit = AsyncMock()

    with pytest.raises(HTTPException) as excinfo:
        await qa_handlers.update_manual_result(
            bud_id=bud.id,
            body=ManualTestResultUpdate(test_case_id="MTC-999", result="pending"),
            db=fake_db,
            current_user=fake_user,
        )
    assert excinfo.value.status_code == 404
