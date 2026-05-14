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

"""Handler-level tests for the BUD section edit-gating policy.

Verifies the two HTTP entry points that can mutate a section — the
JSON PATCH and the markdown upload — both raise HTTP 409
``bud_section_locked`` when the BUD is out of phase, and that
non-section fields stay writeable.

Following the existing pattern in this directory (``conftest.py``
explains why): no DB scaffolding, no live FastAPI server — handler
functions are imported and invoked with mocked sessions / repos. The
underlying gate (``services/bud_edit_policy``) is unit-tested in
``tests/services/test_bud_edit_policy.py``; this file is the
contract test between the handlers and the gate.
"""

from __future__ import annotations

import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1 import bud as bud_handlers
from app.models.bud import BUDStatus
from app.schemas.bud import BUDUpdate


def _make_bud(status: BUDStatus) -> SimpleNamespace:
    """Minimal BUD stand-in for the gating paths (no DB load)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        bud_number=1,
        title="Test BUD",
        status=status,
        assignee_id=None,
        requirements_md=None,
        tech_spec_md=None,
        test_plan_md=None,
        code_review_comments=None,
        impacted_repos=None,
        qa_manual_cases=None,
    )


def _patch_bud_repo(monkeypatch: pytest.MonkeyPatch, bud: SimpleNamespace) -> None:
    """Make ``BUDRepository(...).get_by_id(...)`` return ``bud``."""
    repo = MagicMock(get_by_id=AsyncMock(return_value=bud))
    monkeypatch.setattr(bud_handlers, "BUDRepository", MagicMock(return_value=repo))


# ``fake_user`` and ``fake_db`` come from tests/api/v1/conftest.py.


# ── PATCH /buds/{id} ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_requirements_outside_bud_phase_returns_409(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """PATCH ``requirements_md`` while the BUD is in development → 409."""
    bud = _make_bud(BUDStatus.DEVELOPMENT)
    _patch_bud_repo(monkeypatch, bud)

    body = BUDUpdate(requirements_md="hack-attempt")
    with pytest.raises(HTTPException) as excinfo:
        await bud_handlers.update_bud(
            bud_id=bud.id,
            body=body,
            response=MagicMock(),
            current_user=fake_user,
            db=fake_db,
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "bud_section_locked"
    assert excinfo.value.detail["field"] == "requirements_md"
    assert excinfo.value.detail["current_status"] == "development"
    assert excinfo.value.detail["required_status"] == "bud"

    # Defense in depth: the rejected request must not have mutated the
    # BUD or flushed the session.
    assert bud.requirements_md is None
    fake_db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_patch_title_is_always_allowed(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """Non-section fields (``title``) bypass the gate even from PROD."""
    bud = _make_bud(BUDStatus.PROD)
    _patch_bud_repo(monkeypatch, bud)
    # Patch out everything else PATCH touches so the call doesn't blow
    # up downstream — we only care that the gate doesn't reject title.
    monkeypatch.setattr(bud_handlers, "_bud_response", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr("app.services.bud_timeline.record_event", AsyncMock(return_value=None))

    body = BUDUpdate(title="Renamed during prod")
    # Must not raise — the BUDEditPolicy is the only gate under test;
    # any other downstream error means our patches are incomplete, not
    # that the gate fired.
    await bud_handlers.update_bud(
        bud_id=bud.id,
        body=body,
        response=MagicMock(),
        current_user=fake_user,
        db=fake_db,
    )


# ── POST /buds/{id}/import/{section} ───────────────────────────────────


@pytest.mark.asyncio
async def test_import_section_outside_phase_returns_409(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """Upload markdown to ``requirements_md`` during development → 409."""
    bud = _make_bud(BUDStatus.DEVELOPMENT)
    _patch_bud_repo(monkeypatch, bud)

    upload = UploadFile(filename="r.md", file=BytesIO(b"# new requirements"))
    with pytest.raises(HTTPException) as excinfo:
        await bud_handlers.import_bud_section(
            bud_id=bud.id,
            section="requirements_md",
            file=upload,
            current_user=fake_user,
            db=fake_db,
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "bud_section_locked"
    assert excinfo.value.detail["field"] == "requirements_md"

    # Same defense-in-depth check: the bud must not have been written.
    assert bud.requirements_md is None
    fake_db.flush.assert_not_called()
