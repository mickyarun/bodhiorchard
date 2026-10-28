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

"""Handler-level tests for the design-file upload endpoint.

Covers the ``POST /buds/{id}/designs/upload`` multipart path that lets a
browser attach a self-contained wireframe HTML file directly, bypassing
the inline-content write that times out on large designs — plus how it
and ``generate_designs`` turn the design repository's cross-tenant refusal
into a 404. Follows the direct-handler pattern of this directory
(see ``conftest.py``): route functions are invoked with mocked
repos/session, so these assert the handler's own guards and its contract
with the repo + timeline layers, not the DB.
"""

from __future__ import annotations

import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1 import bud_designs
from app.models.bud import BUDDesignStatus, BUDStatus
from app.repositories.bud import DesignTargetNotInOrgError
from app.schemas.bud_design import DesignGenerateRequest


def _make_bud(status: BUDStatus) -> SimpleNamespace:
    """Minimal BUD stand-in for the design-upload path."""
    return SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), status=status)


def _patch_repos(
    monkeypatch: pytest.MonkeyPatch,
    bud: SimpleNamespace,
    design_id: uuid.UUID,
) -> tuple[MagicMock, MagicMock]:
    """Wire ``BUDRepository`` + ``BUDDesignRepository`` to in-memory fakes.

    Returns the design-repo instance mock and the ``record_event`` mock so
    tests can assert the upsert + credit contract.
    """
    bud_repo = MagicMock(get_by_id=AsyncMock(return_value=bud))
    monkeypatch.setattr(bud_designs, "BUDRepository", MagicMock(return_value=bud_repo))

    design = SimpleNamespace(id=design_id)
    design_repo = MagicMock(
        upsert=AsyncMock(return_value=design),
        list_with_repo_names=AsyncMock(
            return_value=[{"id": design_id, "repo_id": None, "repo_name": None}]
        ),
    )
    monkeypatch.setattr(bud_designs, "BUDDesignRepository", MagicMock(return_value=design_repo))

    record_event = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_designs, "record_event", record_event)
    return design_repo, record_event


def _html_upload(body: bytes, filename: str = "wire.html") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(body))


@pytest.mark.asyncio
async def test_upload_persists_ready_design_and_credits_uploader(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """Happy path: HTML file → sanitized upsert marked READY + timeline credit."""
    bud = _make_bud(BUDStatus.DESIGN)
    design_id = uuid.uuid4()
    design_repo, record_event = _patch_repos(monkeypatch, bud, design_id)

    result = await bud_designs.upload_design(
        bud_id=bud.id,
        file=_html_upload(b"<html><body>hi</body></html>"),
        repo_id=None,
        notes=None,
        current_user=fake_user,
        db=fake_db,
    )

    assert result["id"] == design_id
    design_repo.upsert.assert_awaited_once()
    # Upserted as READY so the tab renders immediately (no generating spinner).
    assert design_repo.upsert.await_args.kwargs["status"] == BUDDesignStatus.READY
    assert design_repo.upsert.await_args.kwargs["design_html"]
    # The uploader is credited via a design_updated event for the SP rule.
    record_event.assert_awaited_once()
    assert record_event.await_args.args[3] == "design_updated"
    assert record_event.await_args.kwargs["actor_id"] == fake_user.id


@pytest.mark.asyncio
async def test_upload_out_of_phase_returns_409(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """A BUD outside the design phase rejects uploads with 409 — no write."""
    bud = _make_bud(BUDStatus.DEVELOPMENT)
    design_repo, _ = _patch_repos(monkeypatch, bud, uuid.uuid4())

    with pytest.raises(HTTPException) as excinfo:
        await bud_designs.upload_design(
            bud_id=bud.id,
            file=_html_upload(b"<html></html>"),
            repo_id=None,
            notes=None,
            current_user=fake_user,
            db=fake_db,
        )

    assert excinfo.value.status_code == 409
    design_repo.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_foreign_repo_id_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """The repository refuses a repo_id outside the caller's org → 404, no event."""
    bud = _make_bud(BUDStatus.DESIGN)
    design_repo, record_event = _patch_repos(monkeypatch, bud, uuid.uuid4())
    foreign_repo = uuid.uuid4()
    design_repo.upsert.side_effect = DesignTargetNotInOrgError("repo", foreign_repo)

    with pytest.raises(HTTPException) as excinfo:
        await bud_designs.upload_design(
            bud_id=bud.id,
            file=_html_upload(b"<html><body>x</body></html>"),
            repo_id=foreign_repo,
            notes=None,
            current_user=fake_user,
            db=fake_db,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Repository not found"
    record_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_designs_foreign_repo_id_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """generate_designs turns a foreign repo_id into a 404 — no job enqueued.

    The repository refuses the repo before writing a row, and the 404 is
    raised before any job is created, so a crafted repo_ids list can't seed
    design rows or design runs against another tenant's repository.
    """
    bud = _make_bud(BUDStatus.DESIGN)
    design_repo, _ = _patch_repos(monkeypatch, bud, uuid.uuid4())
    foreign_repo = uuid.uuid4()
    design_repo.upsert.side_effect = DesignTargetNotInOrgError("repo", foreign_repo)
    monkeypatch.setattr(bud_designs, "_assert_design_system_available", AsyncMock())
    create_job = MagicMock()
    monkeypatch.setattr(bud_designs, "create_job", create_job)

    with pytest.raises(HTTPException) as excinfo:
        await bud_designs.generate_designs(
            bud_id=bud.id,
            body=DesignGenerateRequest(repo_ids=[foreign_repo]),
            current_user=fake_user,
            db=fake_db,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Repository not found"
    create_job.assert_not_called()


@pytest.mark.asyncio
async def test_upload_non_html_rejected(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """A non-.html filename with no html content-type → 400 before any read."""
    bud = _make_bud(BUDStatus.DESIGN)
    design_repo, _ = _patch_repos(monkeypatch, bud, uuid.uuid4())

    with pytest.raises(HTTPException) as excinfo:
        await bud_designs.upload_design(
            bud_id=bud.id,
            file=_html_upload(b"not html", filename="notes.txt"),
            repo_id=None,
            notes=None,
            current_user=fake_user,
            db=fake_db,
        )

    assert excinfo.value.status_code == 400
    design_repo.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_empty_file_rejected(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """Whitespace-only HTML is treated as empty → 400."""
    bud = _make_bud(BUDStatus.DESIGN)
    design_repo, _ = _patch_repos(monkeypatch, bud, uuid.uuid4())

    with pytest.raises(HTTPException) as excinfo:
        await bud_designs.upload_design(
            bud_id=bud.id,
            file=_html_upload(b"   \n  "),
            repo_id=None,
            notes=None,
            current_user=fake_user,
            db=fake_db,
        )

    assert excinfo.value.status_code == 400
    design_repo.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_over_size_limit_rejected(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """A payload past the byte cap → 413, without touching the repo."""
    bud = _make_bud(BUDStatus.DESIGN)
    design_repo, _ = _patch_repos(monkeypatch, bud, uuid.uuid4())
    monkeypatch.setattr(bud_designs, "MAX_DESIGN_UPLOAD_BYTES", 8)

    with pytest.raises(HTTPException) as excinfo:
        await bud_designs.upload_design(
            bud_id=bud.id,
            file=_html_upload(b"<html>way too many bytes</html>"),
            repo_id=None,
            notes=None,
            current_user=fake_user,
            db=fake_db,
        )

    assert excinfo.value.status_code == 413
    design_repo.upsert.assert_not_awaited()
