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

"""QA test case management API endpoints.

Provides CRUD for QA test results, evidence upload/download,
and summary statistics for the QA/Testing phase of the BUD pipeline.
"""

import os
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.qa_test_evidence import QATestEvidence
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.qa_test_evidence import QATestEvidenceRepository
from app.schemas.qa import (
    ManualTestResultUpdate,
    QASummaryResponse,
    QATestCasesResponse,
    TestEvidenceRead,
)
from app.services.file_storage import MAX_FILE_SIZE, FileStorageError, get_file_storage

logger = structlog.get_logger(__name__)

router = APIRouter()


# Anything outside this set is replaced with ``_`` in the storage
# filename. We intentionally allow only ASCII alphanumerics, dot,
# dash, and underscore — that is the strict subset that survives
# unchanged in: S3 object keys, every supported local filesystem,
# the ``Content-Disposition: filename="..."`` header (latin-1 only),
# and ``mimetypes.guess_type`` extension matching.
_FILENAME_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_REPEATED_UNDERSCORE_RE = re.compile(r"_+")


def _sanitize_filename(name: str | None) -> str:
    """Normalise a user-supplied filename to an ASCII-safe storage name.

    The previous implementation just ran ``os.path.basename`` and
    trusted the user's name. That left `` `` (narrow no-break
    space, common in macOS screenshot timestamps like
    ``Screenshot 2026-05-20 at 4.00.01 PM.png``) in the value, which
    crashed downloads at the ``Content-Disposition`` header-encode
    step with ``UnicodeEncodeError: 'latin-1' codec can't encode
    character``. Normalising at upload time keeps both the storage
    path AND the DB-stored filename strictly latin-1 — downloads
    never have to think about Unicode.

    NFKD decomposes accented chars into base + combining marks,
    ``encode("ascii", "ignore")`` then strips the combining marks
    (so "café" → "cafe", not "caf"). Whatever remains that isn't
    ``[A-Za-z0-9._-]`` becomes ``_``; runs of underscores collapse
    to one; empty stems fall back to ``"evidence"``.
    """
    base = os.path.basename(name or "evidence")
    if not base:
        base = "evidence"

    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""

    # NFKD → ASCII fold so "Café résumé.PDF" → "Cafe resume.PDF"
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    ext = unicodedata.normalize("NFKD", ext).encode("ascii", "ignore").decode("ascii")

    # Replace remaining unsafe chars, collapse repeats, trim ``_``s
    stem = _FILENAME_UNSAFE_RE.sub("_", stem)
    stem = _REPEATED_UNDERSCORE_RE.sub("_", stem).strip("_")
    # Strip leading/trailing dots so all-dots inputs ("...", "..")
    # don't survive as path-traversal-looking segments. ``strip(".")``
    # AFTER underscore trimming handles ``__.__`` patterns too.
    stem = stem.strip(".")
    ext = _FILENAME_UNSAFE_RE.sub("", ext)[:10]  # cap extension length

    if not stem:
        stem = "evidence"
    return f"{stem}.{ext}" if ext else stem


@router.get(
    "/test-cases",
    response_model=QATestCasesResponse,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_test_cases(
    bud_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QATestCasesResponse:
    """Return all QA test cases for a BUD from dedicated columns."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if not bud:
        raise HTTPException(status_code=404, detail="BUD not found")

    evidence_repo = QATestEvidenceRepository(db, org_id=current_user.org_id)
    evidence_rows = await evidence_repo.list_for_bud(bud_id)

    return QATestCasesResponse(
        automation_test_cases=bud.qa_automation_cases or [],
        manual_test_cases=bud.qa_manual_cases or [],
        execution_plan_md=bud.qa_execution_plan_md or "",
        evidence=[TestEvidenceRead.model_validate(e) for e in evidence_rows],
    )


@router.patch(
    "/manual-results",
    dependencies=[Depends(require_permissions("buds:edit", "buds:test", mode="any"))],
)
async def update_manual_result(
    bud_id: uuid.UUID,
    body: ManualTestResultUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Update the result of a manual test case (pass/fail/blocked/skipped)."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)

    # Row-level lock to prevent concurrent metadata overwrites
    bud = await bud_repo.get_by_id_for_update(bud_id)
    if not bud:
        raise HTTPException(status_code=404, detail="BUD not found")

    manual_cases: list[dict[str, Any]] = list(bud.qa_manual_cases or [])

    # Find and update the target case
    found = False
    for case in manual_cases:
        if case.get("id") == body.test_case_id:
            case["result"] = body.result
            case["tester_name"] = current_user.name
            case["tested_at"] = datetime.now(UTC).isoformat()
            if body.notes:
                case["notes"] = body.notes
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Test case {body.test_case_id} not found")

    bud.qa_manual_cases = manual_cases
    flag_modified(bud, "qa_manual_cases")
    await db.commit()

    return {"status": "updated", "test_case_id": body.test_case_id}


@router.post(
    "/evidence/{test_case_id}",
    response_model=TestEvidenceRead,
    dependencies=[Depends(require_permissions("buds:edit", "buds:test", mode="any"))],
)
async def upload_evidence(
    bud_id: uuid.UUID,
    test_case_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TestEvidenceRead:
    """Upload an evidence file for a manual test case."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if not bud:
        raise HTTPException(status_code=404, detail="BUD not found")

    # Sanitise the user-supplied filename to an ASCII-safe form. This
    # is used in BOTH the storage path AND the DB ``filename`` column,
    # so the Content-Disposition header on download is latin-1 clean
    # without any further escaping.
    safe_filename = _sanitize_filename(file.filename)

    # Read with size cap to prevent memory exhaustion before storage
    # validation. Keep this in lockstep with ``MAX_FILE_SIZE`` in
    # ``app/services/file_storage.py`` — the shared comment block there
    # lists every other place the limit is enforced.
    max_upload = MAX_FILE_SIZE + 1  # +1 byte to detect overflow
    data = await file.read(max_upload)
    if len(data) >= max_upload:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_FILE_SIZE // (1024 * 1024)} MB limit",
        )
    content_type = file.content_type or "application/octet-stream"

    # Storage layout:
    #
    #   {org_id}/qa-evidence/BUD-{nnn}/{MTC-xxx}/{evidence-uuid}-{safe_name}
    #
    # ``BUD-{nnn}`` is the human-readable per-org BUD number (matches
    # what shows in the UI / branch names like ``bud-007/...``) so
    # operators browsing S3 don't have to look up UUIDs. The
    # ``evidence-uuid`` prefix on the filename guarantees no
    # overwrites when two files of the same name land on the same
    # test case (the previous flat layout silently clobbered them).
    storage = get_file_storage()
    bud_label = f"BUD-{bud.bud_number:03d}"
    evidence_key = uuid.uuid4().hex[:12]
    storage_filename = f"{evidence_key}-{safe_filename}"
    relative_path = f"qa-evidence/{bud_label}/{test_case_id}/{storage_filename}"

    try:
        storage_path = await storage.upload(
            org_id=str(current_user.org_id),
            relative_path=relative_path,
            data=data,
            content_type=content_type,
        )
    except FileStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    evidence_repo = QATestEvidenceRepository(db, org_id=current_user.org_id)
    evidence = await evidence_repo.create(
        QATestEvidence(
            org_id=current_user.org_id,
            bud_id=bud_id,
            test_case_id=test_case_id,
            filename=safe_filename,
            mime_type=content_type,
            storage_path=storage_path,
            uploaded_by=current_user.id,
        )
    )
    await db.commit()

    return TestEvidenceRead.model_validate(evidence)


@router.get(
    "/evidence/{evidence_id}",
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def download_evidence(
    bud_id: uuid.UUID,
    evidence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Download an evidence file."""
    evidence_repo = QATestEvidenceRepository(db, org_id=current_user.org_id)
    evidence = await evidence_repo.get_by_id(evidence_id)
    if not evidence or evidence.bud_id != bud_id:
        raise HTTPException(status_code=404, detail="Evidence not found")

    storage = get_file_storage()
    try:
        data, content_type = await storage.download(evidence.storage_path)
    except FileStorageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Sanitise the on-disk filename for the ``Content-Disposition``
    # header. New uploads already store ASCII-safe names (see
    # ``_sanitize_filename`` at upload time), but pre-existing rows
    # may carry `` `` / accented / CJK characters that would
    # otherwise crash Starlette's latin-1 header encoder with
    # ``UnicodeEncodeError``. Running the same sanitiser here is the
    # belt to the upload path's braces.
    safe_name = _sanitize_filename(evidence.filename)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.delete(
    "/evidence/{evidence_id}",
    dependencies=[Depends(require_permissions("buds:edit", "buds:test", mode="any"))],
)
async def delete_evidence(
    bud_id: uuid.UUID,
    evidence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Delete an evidence file (DB row + storage)."""
    evidence_repo = QATestEvidenceRepository(db, org_id=current_user.org_id)
    evidence = await evidence_repo.get_by_id(evidence_id)
    if not evidence or evidence.bud_id != bud_id:
        raise HTTPException(status_code=404, detail="Evidence not found")

    storage = get_file_storage()
    await storage.delete(evidence.storage_path)
    await evidence_repo.delete(evidence)
    await db.commit()

    return {"status": "deleted", "evidence_id": str(evidence_id)}


@router.get(
    "/summary",
    response_model=QASummaryResponse,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_qa_summary(
    bud_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QASummaryResponse:
    """Return pass/fail/pending counts for QA progress tracking."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if not bud:
        raise HTTPException(status_code=404, detail="BUD not found")

    manual_cases: list[dict[str, Any]] = bud.qa_manual_cases or []
    auto_cases: list[dict[str, Any]] = bud.qa_automation_cases or []

    evidence_repo = QATestEvidenceRepository(db, org_id=current_user.org_id)
    evidence_count = len(await evidence_repo.list_for_bud(bud_id))

    results = [c.get("result", "pending") for c in manual_cases]

    return QASummaryResponse(
        total_automation=len(auto_cases),
        total_manual=len(manual_cases),
        manual_pass=results.count("pass"),
        manual_fail=results.count("fail"),
        manual_blocked=results.count("blocked"),
        manual_skipped=results.count("skipped"),
        manual_pending=results.count("pending"),
        evidence_count=evidence_count,
    )
