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
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.file_storage import FileStorageError, get_file_storage

logger = structlog.get_logger(__name__)

router = APIRouter()


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
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def update_manual_result(
    bud_id: uuid.UUID,
    body: ManualTestResultUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Update the result of a manual test case (pass/fail/blocked/skipped)."""
    from datetime import UTC, datetime

    bud_repo = BUDRepository(db, org_id=current_user.org_id)

    # Row-level lock to prevent concurrent metadata overwrites
    bud = await bud_repo.get_by_id_for_update(bud_id)
    if not bud:
        raise HTTPException(status_code=404, detail="BUD not found")

    manual_cases: list[dict] = list(bud.qa_manual_cases or [])

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

    from sqlalchemy.orm.attributes import flag_modified

    bud.qa_manual_cases = manual_cases
    flag_modified(bud, "qa_manual_cases")
    await db.commit()

    return {"status": "updated", "test_case_id": body.test_case_id}


@router.post(
    "/evidence/{test_case_id}",
    response_model=TestEvidenceRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
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

    # Sanitize filename to prevent path traversal
    safe_filename = os.path.basename(file.filename or "evidence")

    # Read with size cap to prevent memory exhaustion before storage validation
    max_upload = 10 * 1024 * 1024 + 1  # 10 MB + 1 byte to detect overflow
    data = await file.read(max_upload)
    if len(data) >= max_upload:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")
    content_type = file.content_type or "application/octet-stream"

    storage = get_file_storage()
    relative_path = f"qa-evidence/{bud_id}/{test_case_id}/{safe_filename}"

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

    # Sanitize filename for Content-Disposition header (prevent header injection)
    safe_name = evidence.filename.replace('"', "_").replace("\n", "_").replace("\r", "_")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.delete(
    "/evidence/{evidence_id}",
    dependencies=[Depends(require_permissions("buds:edit"))],
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

    manual_cases: list[dict] = bud.qa_manual_cases or []
    auto_cases: list[dict] = bud.qa_automation_cases or []

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
