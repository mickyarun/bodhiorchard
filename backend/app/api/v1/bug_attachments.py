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

"""Bug attachment endpoints — list, upload, download, delete.

Reporters attach the evidence that makes a bug reproducible: a
screenshot of the broken screen, a PDF of the failing report, the
spreadsheet whose export is wrong. Accepted types are fixed in
``app.services.upload_policy``; the size and count limits are per-org
(Settings → QA Automation & BUD Stages) and resolved per request.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_current_user,
    get_db,
    get_user_permissions,
    require_permissions,
)
from app.core.paths import sanitize_filename
from app.models.bug import Bug
from app.models.bug_attachment import BugAttachment
from app.models.user import User
from app.repositories.bug import BugRepository
from app.repositories.bug_attachment import BugAttachmentRepository
from app.repositories.organization import OrganizationRepository
from app.schemas.bug import (
    BugAttachmentLimits,
    BugAttachmentListResponse,
    BugAttachmentRead,
)
from app.services.file_storage import FileStorageError, get_file_storage
from app.services.org_settings import get_bug_attachment_settings
from app.services.upload_policy import UploadPolicy, UploadPolicyError, bug_attachment_policy

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["bug-attachments"])

# Dual-gate, matching ``bug_comments``: ``bugs:*`` is canonical, the
# legacy ``buds:*`` fallbacks keep pre-Step-E role tokens working.
#
# Attaching is gated on the same permissions as reporting, not on
# ``bugs:edit`` — a reporter who can file a bug must be able to attach
# the screenshot that explains it, or the feature is unusable by the
# people it exists for.
#
# TODO(step-e-cleanup): drop the legacy fallbacks once all orgs have
# re-seeded. Search for this marker to find every dual-gate call site.
_VIEW_PERMS = ("bugs:view", "buds:view")
_ATTACH_PERMS = ("bugs:report", "bugs:edit", "buds:edit")


@router.get(
    "/attachments/limits",
    response_model=BugAttachmentLimits,
    response_model_by_alias=True,
    dependencies=[Depends(require_permissions(*_VIEW_PERMS, mode="any"))],
)
async def get_attachment_limits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugAttachmentLimits:
    """Return this org's attachment limits without naming a bug.

    The create dialog stages files before the bug exists, so it has no
    list response to read limits from. Without this the picker would
    fall back to the shipped defaults and wrongly reject a file that an
    org with a *higher* cap actually allows.

    Two path segments keep this clear of ``GET /bugs/{bug_id}``, which
    is registered first and would otherwise swallow it and 422 on the
    UUID parse.
    """
    policy = await _resolve_policy(db, current_user.org_id)
    return _limits_of(policy)


@router.get(
    "/{bug_id}/attachments",
    response_model=BugAttachmentListResponse,
    response_model_by_alias=True,
    dependencies=[Depends(require_permissions(*_VIEW_PERMS, mode="any"))],
)
async def list_bug_attachments(
    bug_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugAttachmentListResponse:
    """List a bug's attachments together with the org's current limits."""
    await _ensure_bug_in_org(db, current_user.org_id, bug_id)
    policy = await _resolve_policy(db, current_user.org_id)

    rows = await BugAttachmentRepository(db, org_id=current_user.org_id).list_for_bug(bug_id)
    return BugAttachmentListResponse(
        items=[BugAttachmentRead.model_validate(row) for row in rows],
        limits=_limits_of(policy),
    )


@router.post(
    "/{bug_id}/attachments",
    response_model=BugAttachmentRead,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(*_ATTACH_PERMS, mode="any"))],
)
async def upload_bug_attachment(
    bug_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugAttachmentRead:
    """Attach one file to a bug.

    Validation runs in the order that keeps the most expensive work
    last: the per-bug count first (a cheap COUNT), then the type (from
    the filename alone), then the bytes — so a reporter at the file cap
    is told immediately instead of after uploading 10 MB.
    """
    bug = await _ensure_bug_in_org(db, current_user.org_id, bug_id)
    policy = await _resolve_policy(db, current_user.org_id)
    attachment_repo = BugAttachmentRepository(db, org_id=current_user.org_id)

    existing = await attachment_repo.count_for_bug(bug_id)
    try:
        policy.check_count(existing)
    except UploadPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # ASCII-safe for BOTH the storage path and the DB ``filename``
    # column, so the download route's Content-Disposition header is
    # latin-1 clean without further escaping.
    safe_filename = sanitize_filename(file.filename, fallback="attachment")

    # Canonical type from the extension, never the browser's
    # Content-Type — see ``upload_policy`` for why that header can't be
    # trusted for spreadsheets. Resolving against the sanitised name
    # also means a rejected extension can't have survived sanitisation
    # as something else.
    try:
        content_type = policy.resolve_mime(safe_filename)
    except UploadPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Read one byte past the cap so an oversized file is detected
    # without buffering the whole of it in memory.
    data = await file.read(policy.max_bytes + 1)
    if len(data) > policy.max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{policy.label} exceeds the {policy.max_mb} MB limit.",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{safe_filename} is empty.",
        )

    # Storage layout:
    #
    #   {org_id}/bug-attachments/BUG-{nnn}/{key}-{safe_name}
    #
    # ``BUG-{nnn}`` is the human-readable per-org bug number, so an
    # operator browsing the bucket doesn't have to resolve UUIDs. The
    # random key prefix keeps two files of the same name on one bug
    # from clobbering each other.
    storage = get_file_storage()
    relative_path = (
        f"bug-attachments/BUG-{bug.bug_number:03d}/{uuid.uuid4().hex[:12]}-{safe_filename}"
    )
    try:
        storage_path = await storage.upload(
            org_id=str(current_user.org_id),
            relative_path=relative_path,
            data=data,
            content_type=content_type,
            policy=policy,
        )
    except FileStorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    attachment = await attachment_repo.create(
        BugAttachment(
            org_id=current_user.org_id,
            bug_id=bug_id,
            filename=safe_filename,
            mime_type=content_type,
            size_bytes=len(data),
            storage_path=storage_path,
            uploaded_by=current_user.id,
        )
    )
    await db.commit()

    logger.info(
        "bug_attachment_uploaded",
        bug_id=str(bug_id),
        attachment_id=str(attachment.id),
        mime_type=content_type,
        size=len(data),
    )
    return BugAttachmentRead.model_validate(attachment)


@router.get(
    "/{bug_id}/attachments/{attachment_id}",
    dependencies=[Depends(require_permissions(*_VIEW_PERMS, mode="any"))],
)
async def download_bug_attachment(
    bug_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream one attachment's bytes back to an authorised caller."""
    attachment = await _get_attachment(db, current_user.org_id, bug_id, attachment_id)

    storage = get_file_storage()
    try:
        data, _stored_type = await storage.download(attachment.storage_path)
    except FileStorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Serve the type recorded at upload, which we derived ourselves from
    # the extension, rather than whatever the storage backend reports —
    # the local backend guesses from the path and S3 echoes what was put.
    #
    # The filename is already ASCII-safe from upload-time sanitisation;
    # re-running the sanitiser covers any row written before that
    # guarantee existed, and keeps the header latin-1 clean.
    safe_name = sanitize_filename(attachment.filename, fallback="attachment")
    return Response(
        content=data,
        media_type=attachment.mime_type,
        headers={
            # ``attachment``, matching the QA evidence route. Nothing in
            # the UI reads this header - tiles fetch the bytes over XHR
            # and render a blob URL - so serving user content inline
            # would buy nothing while leaving a same-origin browsing
            # context available to a future cookie session or iframe
            # preview. The two headers below hold that line regardless:
            #   * nosniff stops a browser ignoring our declared type and
            #     executing, say, a .png full of HTML;
            #   * the sandbox CSP strips scripting and same-origin
            #     access, which matters for PDFs (they can carry JS).
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.delete(
    "/{bug_id}/attachments/{attachment_id}",
    dependencies=[Depends(require_permissions(*_ATTACH_PERMS, mode="any"))],
)
async def delete_bug_attachment(
    bug_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete an attachment — uploader-only, with a ``bugs:edit`` override.

    Hard delete: unlike a comment there is nothing to tombstone, and
    leaving the bytes behind would keep counting against the per-bug
    limit.

    Storage is cleared first so a storage failure aborts before the row
    is touched, leaving a consistent state the user can retry. The
    reverse gap stays open - a failure between the object delete and
    the commit leaves a row pointing at bytes that are gone - but both
    backends delete idempotently, so that retry succeeds, whereas a row
    deleted first would strand the object with nothing referencing it.
    """
    attachment = await _get_attachment(db, current_user.org_id, bug_id, attachment_id)
    await _ensure_can_delete(current_user, attachment, db)

    storage = get_file_storage()
    try:
        await storage.delete(attachment.storage_path)
    except FileStorageError as exc:
        # The row stays, so the file is still listed and the user can
        # retry once the backend recovers — better than a dangling row
        # pointing at bytes we failed to remove.
        logger.error(
            "bug_attachment_delete_failed",
            attachment_id=str(attachment_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not remove the stored file. Try again.",
        ) from exc

    repo = BugAttachmentRepository(db, org_id=current_user.org_id)
    await repo.delete(attachment)
    await db.commit()

    return {"status": "deleted", "attachment_id": str(attachment_id)}


# ── Helpers ──────────────────────────────────────────────────────────


async def _ensure_bug_in_org(db: AsyncSession, org_id: uuid.UUID, bug_id: uuid.UUID) -> Bug:
    """Return the bug, or 404 when it is missing or in another org."""
    bug = await BugRepository(db, org_id=org_id).get_by_id(bug_id)
    if bug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bug not found")
    return bug


async def _get_attachment(
    db: AsyncSession,
    org_id: uuid.UUID,
    bug_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> BugAttachment:
    """Fetch an attachment, 404ing unless it belongs to this bug and org."""
    attachment = await BugAttachmentRepository(db, org_id=org_id).get_by_id(attachment_id)
    if attachment is None or attachment.bug_id != bug_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment


async def _ensure_can_delete(
    current_user: User,
    attachment: BugAttachment,
    db: AsyncSession,
) -> None:
    """Uploaders may always remove their own file; editors may remove any.

    Mirrors the comment-thread rule. Without the uploader check, anyone
    holding only ``bugs:report`` could delete a colleague's evidence.
    """
    if attachment.uploaded_by == current_user.id:
        return
    perms = await get_user_permissions(current_user, db)
    if "bugs:edit" in perms or "buds:edit" in perms:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the person who uploaded this file may remove it.",
    )


async def _resolve_policy(db: AsyncSession, org_id: uuid.UUID) -> UploadPolicy:
    """Build the upload policy from this org's configured limits.

    A missing org row falls back to the shipped defaults rather than
    failing the request: the caller is already authenticated against
    that org, so an absent row is an internal inconsistency, not a
    reason to block someone from attaching a screenshot.
    """
    cfg = get_bug_attachment_settings(await OrganizationRepository(db).get_config(org_id))
    return bug_attachment_policy(
        max_file_mb=cfg.max_file_mb,
        max_files=cfg.max_files_per_bug,
    )


def _limits_of(policy: UploadPolicy) -> BugAttachmentLimits:
    """Project the policy into the client-facing limits payload."""
    return BugAttachmentLimits(
        max_file_mb=policy.max_mb,
        max_files_per_bug=policy.max_files or 0,
        accepted_extensions=sorted(policy.extensions or {}),
    )
