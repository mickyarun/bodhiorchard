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

"""Handler-level tests for the bug-attachment routes.

The feature is a tenant-isolation surface with a hand-rolled delete
authorization branch, so these cover the guards rather than the happy
path alone: cross-org and cross-bug lookups, the per-org count and type
gates, and who may remove whose file.

Follows the direct-handler pattern of this directory (see
``conftest.py``): route functions are invoked with mocked repos and
session, so they assert the handler's own logic and its contract with
the repo / storage layers, not the DB.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1 import bug_attachments
from app.services.file_storage import FileStorageError

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()


def _user(user_id: uuid.UUID | None = None, org_id: uuid.UUID = ORG_ID) -> SimpleNamespace:
    """Minimal authenticated-user stand-in."""
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        org_id=org_id,
        name="Tester",
        email="tester@example.com",
    )


def _bug(bug_number: int = 7) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), org_id=ORG_ID, bug_number=bug_number)


def _attachment(
    bug_id: uuid.UUID,
    uploaded_by: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        bug_id=bug_id,
        org_id=ORG_ID,
        filename="shot.png",
        mime_type="image/png",
        size_bytes=1024,
        storage_path=f"{ORG_ID}/bug-attachments/BUG-007/abc-shot.png",
        uploaded_by=uploaded_by,
        created_at=None,
    )


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    bug: SimpleNamespace | None,
    attachment: SimpleNamespace | None = None,
    existing_count: int = 0,
    max_files: int = 10,
    max_file_mb: int = 10,
) -> tuple[MagicMock, MagicMock]:
    """Wire the repos, org settings and storage to in-memory fakes.

    Returns the attachment-repo and storage mocks so tests can assert
    what the handler asked them to do.
    """
    monkeypatch.setattr(
        bug_attachments,
        "BugRepository",
        MagicMock(return_value=MagicMock(get_by_id=AsyncMock(return_value=bug))),
    )

    attachment_repo = MagicMock(
        get_by_id=AsyncMock(return_value=attachment),
        list_for_bug=AsyncMock(return_value=[attachment] if attachment else []),
        count_for_bug=AsyncMock(return_value=existing_count),
        create=AsyncMock(side_effect=_stamp_defaults),
        delete=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        bug_attachments, "BugAttachmentRepository", MagicMock(return_value=attachment_repo)
    )

    # The handler reads org config through the repository layer, so the
    # fake has to live there rather than on `db.get`.
    monkeypatch.setattr(
        bug_attachments,
        "OrganizationRepository",
        MagicMock(return_value=MagicMock(get_config=AsyncMock(return_value={}))),
    )
    monkeypatch.setattr(
        bug_attachments,
        "get_bug_attachment_settings",
        MagicMock(
            return_value=SimpleNamespace(max_file_mb=max_file_mb, max_files_per_bug=max_files)
        ),
    )

    storage = MagicMock(
        upload=AsyncMock(side_effect=lambda **kw: f"{kw['org_id']}/{kw['relative_path']}"),
        download=AsyncMock(return_value=(b"bytes", "image/png")),
        delete=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(bug_attachments, "get_file_storage", MagicMock(return_value=storage))
    return attachment_repo, storage


def _stamp_defaults(row: object) -> object:
    """Fill the columns Postgres would default on INSERT.

    ``BugAttachmentRepository.create`` flushes and refreshes, so the
    handler sees a row with an id and timestamp. Without a DB those stay
    None and ``BugAttachmentRead.model_validate`` rightly rejects them —
    the stand-in has to model the flush, not skip it.
    """
    row.id = uuid.uuid4()
    row.created_at = datetime(2026, 9, 21, tzinfo=UTC)
    return row


def _db() -> MagicMock:
    """Session stand-in — every query goes through a patched repository."""
    return MagicMock(commit=AsyncMock(return_value=None))


def _upload(name: str = "shot.png", body: bytes = b"binary") -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(body))


# ── Tenant / ownership guards ────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_404s_for_a_bug_in_another_org(monkeypatch: pytest.MonkeyPatch) -> None:
    """The org-scoped repo returns None for a foreign bug — that must 404.

    Guards against a crafted bug id attaching a file to another
    tenant's bug (and leaking its existence through a different code).
    """
    _patch(monkeypatch, bug=None)
    with pytest.raises(HTTPException) as exc:
        await bug_attachments.upload_bug_attachment(
            bug_id=uuid.uuid4(), file=_upload(), current_user=_user(), db=_db()
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_download_404s_when_the_attachment_belongs_to_another_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An attachment id from a different bug must not resolve.

    Org scoping alone wouldn't catch this: both bugs can be in the
    caller's own org.
    """
    bug = _bug()
    other = _attachment(bug_id=uuid.uuid4())
    _patch(monkeypatch, bug=bug, attachment=other)
    with pytest.raises(HTTPException) as exc:
        await bug_attachments.download_bug_attachment(
            bug_id=bug.id, attachment_id=other.id, current_user=_user(), db=_db()
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_is_scoped_to_the_callers_org(monkeypatch: pytest.MonkeyPatch) -> None:
    """The repo is constructed with the caller's org, never a request value."""
    bug = _bug()
    _patch(monkeypatch, bug=bug)
    user = _user(org_id=ORG_ID)
    await bug_attachments.list_bug_attachments(bug_id=bug.id, current_user=user, db=_db())
    repo_cls = bug_attachments.BugAttachmentRepository
    assert all(call.kwargs["org_id"] == ORG_ID for call in repo_cls.call_args_list)
    assert OTHER_ORG_ID not in [c.kwargs.get("org_id") for c in repo_cls.call_args_list]


# ── Upload gates ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_stores_the_canonical_type_not_the_browsers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spreadsheet keeps its real type even when the browser mislabels it.

    Browsers commonly send ``application/octet-stream`` for .xlsx; the
    handler must derive the type from the extension instead.
    """
    bug = _bug()
    repo, storage = _patch(monkeypatch, bug=bug)
    upload = UploadFile(filename="export.xlsx", file=BytesIO(b"xl"))
    result = await bug_attachments.upload_bug_attachment(
        bug_id=bug.id, file=upload, current_user=_user(), db=_db()
    )
    assert result.mime_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert storage.upload.await_args.kwargs["content_type"] == result.mime_type


@pytest.mark.asyncio
async def test_upload_rejects_an_unsupported_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """An .exe is refused with a 400 naming the allowed extensions."""
    bug = _bug()
    _patch(monkeypatch, bug=bug)
    with pytest.raises(HTTPException) as exc:
        await bug_attachments.upload_bug_attachment(
            bug_id=bug.id, file=_upload("payload.exe"), current_user=_user(), db=_db()
        )
    assert exc.value.status_code == 400
    assert ".pdf" in exc.value.detail


@pytest.mark.asyncio
async def test_upload_rejects_once_the_org_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At the per-org cap the next file is refused with a 409."""
    bug = _bug()
    _, storage = _patch(monkeypatch, bug=bug, existing_count=3, max_files=3)
    with pytest.raises(HTTPException) as exc:
        await bug_attachments.upload_bug_attachment(
            bug_id=bug.id, file=_upload(), current_user=_user(), db=_db()
        )
    assert exc.value.status_code == 409
    # Refused before the bytes were read or stored.
    storage.upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_rejects_a_file_over_the_org_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One byte past the org's cap is a 413, and nothing reaches storage."""
    bug = _bug()
    _, storage = _patch(monkeypatch, bug=bug, max_file_mb=1)
    oversized = UploadFile(filename="big.png", file=BytesIO(b"x" * (1024 * 1024 + 1)))
    with pytest.raises(HTTPException) as exc:
        await bug_attachments.upload_bug_attachment(
            bug_id=bug.id, file=oversized, current_user=_user(), db=_db()
        )
    assert exc.value.status_code == 413
    storage.upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_rejects_an_empty_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """A zero-byte pick is a user mistake, not an attachment."""
    bug = _bug()
    _patch(monkeypatch, bug=bug)
    with pytest.raises(HTTPException) as exc:
        await bug_attachments.upload_bug_attachment(
            bug_id=bug.id, file=_upload(body=b""), current_user=_user(), db=_db()
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_sanitises_the_filename_into_the_storage_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode and separators never reach the storage key or the DB row."""
    bug = _bug(bug_number=7)
    _, storage = _patch(monkeypatch, bug=bug)
    weird = UploadFile(filename="../../Café shot.png", file=BytesIO(b"x"))

    result = await bug_attachments.upload_bug_attachment(
        bug_id=bug.id, file=weird, current_user=_user(), db=_db()
    )
    path = storage.upload.await_args.kwargs["relative_path"]
    assert ".." not in path
    assert path.startswith("bug-attachments/BUG-007/")
    assert result.filename == "Cafe_shot.png"


@pytest.mark.asyncio
async def test_upload_surfaces_a_storage_failure_as_a_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A storage error must not become an opaque 500, and must not write a row."""
    bug = _bug()
    repo, storage = _patch(monkeypatch, bug=bug)
    storage.upload = AsyncMock(side_effect=FileStorageError("bucket missing"))
    with pytest.raises(HTTPException) as exc:
        await bug_attachments.upload_bug_attachment(
            bug_id=bug.id, file=_upload(), current_user=_user(), db=_db()
        )
    assert exc.value.status_code == 400
    repo.create.assert_not_awaited()


# ── Delete authorization ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_uploader_may_delete_their_own_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """No extra permission needed to remove a file you added."""
    bug = _bug()
    user = _user()
    attachment = _attachment(bug_id=bug.id, uploaded_by=user.id)
    repo, storage = _patch(monkeypatch, bug=bug, attachment=attachment)
    monkeypatch.setattr(bug_attachments, "get_user_permissions", AsyncMock(return_value=set()))

    result = await bug_attachments.delete_bug_attachment(
        bug_id=bug.id, attachment_id=attachment.id, current_user=user, db=_db()
    )
    assert result["status"] == "deleted"
    storage.delete.assert_awaited_once_with(attachment.storage_path)
    repo.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_reporter_may_not_delete_someone_elses_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``bugs:report`` alone must not let a user wipe a colleague's evidence.

    The upload route is gated on ``bugs:report``, so without this check
    every reporter would inherit delete rights over the whole org.
    """
    bug = _bug()
    attachment = _attachment(bug_id=bug.id, uploaded_by=uuid.uuid4())
    repo, storage = _patch(monkeypatch, bug=bug, attachment=attachment)
    monkeypatch.setattr(
        bug_attachments, "get_user_permissions", AsyncMock(return_value={"bugs:report"})
    )

    with pytest.raises(HTTPException) as exc:
        await bug_attachments.delete_bug_attachment(
            bug_id=bug.id, attachment_id=attachment.id, current_user=_user(), db=_db()
        )
    assert exc.value.status_code == 403
    storage.delete.assert_not_awaited()
    repo.delete.assert_not_awaited()


@pytest.mark.parametrize("permission", ["bugs:edit", "buds:edit"])
@pytest.mark.asyncio
async def test_editors_may_delete_anyones_file(
    monkeypatch: pytest.MonkeyPatch, permission: str
) -> None:
    """Both halves of the dual-gate grant the moderator override."""
    bug = _bug()
    attachment = _attachment(bug_id=bug.id, uploaded_by=uuid.uuid4())
    _patch(monkeypatch, bug=bug, attachment=attachment)
    monkeypatch.setattr(
        bug_attachments, "get_user_permissions", AsyncMock(return_value={permission})
    )

    result = await bug_attachments.delete_bug_attachment(
        bug_id=bug.id, attachment_id=attachment.id, current_user=_user(), db=_db()
    )
    assert result["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_keeps_the_row_when_storage_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A storage failure aborts before the row is removed, so a retry works."""
    bug = _bug()
    user = _user()
    attachment = _attachment(bug_id=bug.id, uploaded_by=user.id)
    repo, storage = _patch(monkeypatch, bug=bug, attachment=attachment)
    storage.delete = AsyncMock(side_effect=FileStorageError("s3 down"))

    with pytest.raises(HTTPException) as exc:
        await bug_attachments.delete_bug_attachment(
            bug_id=bug.id, attachment_id=attachment.id, current_user=user, db=_db()
        )
    assert exc.value.status_code == 502
    repo.delete.assert_not_awaited()


# ── Limits endpoint ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limits_endpoint_reports_the_orgs_configured_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The staged picker's source of truth reflects per-org settings."""
    _patch(monkeypatch, bug=None, max_file_mb=25, max_files=4)
    limits = await bug_attachments.get_attachment_limits(current_user=_user(), db=_db())
    assert limits.max_file_mb == 25
    assert limits.max_files_per_bug == 4
    assert limits.accepted_extensions == [".jpeg", ".jpg", ".pdf", ".png", ".xls", ".xlsx"]
