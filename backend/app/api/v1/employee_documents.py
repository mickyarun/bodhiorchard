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

"""Employee documents: list, upload, open, delete.

HR (employees:documents), the owner, and the employee for their own
documents; only HR deletes. Files are decrypted in memory and never cached.
"""

import uuid
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._employee_helpers import forbid, load_record
from app.core.deps import PermissionSet, get_current_user, get_db, get_permission_set
from app.models.employee_document import DocumentType, EmployeeDocument
from app.models.user import User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_sensitive import EmployeeDocumentRepository
from app.repositories.user import UserRepository
from app.schemas.employee_sensitive import DocumentList, DocumentRead
from app.schemas.leave import PersonRef
from app.services.employees import documents
from app.services.employees.document_policy import MAX_DOCUMENT_BYTES
from app.services.employees.sensitive_access import sensitive_access
from app.services.employees.sensitive_details import Subject
from app.services.upload_policy import UploadPolicyError

router = APIRouter(tags=["employees"])
NO_ACCESS = "Only HR and the employee can see these documents."


async def _reads(db: AsyncSession, docs: list[EmployeeDocument]) -> list[DocumentRead]:
    names = await UserRepository(db).get_names_by_ids(
        {d.uploaded_by for d in docs if d.uploaded_by}
    )
    return [
        DocumentRead(
            id=d.id,
            doc_type=d.doc_type,
            filename=documents.filename_of(d),
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
            uploaded_by=PersonRef(user_id=d.uploaded_by, name=names.get(d.uploaded_by, "Someone"))
            if d.uploaded_by
            else None,
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.get("/{user_id}/documents", response_model=DocumentList)
async def list_documents(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> DocumentList:
    """A person's documents (names only)."""
    access = sensitive_access(perms, current_user.id, user_id)
    if not access.documents:
        raise forbid(NO_ACCESS)
    profile, _user = await load_record(db, current_user.org_id, user_id)
    docs = await EmployeeDocumentRepository(db, org_id=current_user.org_id).list_for_profile(
        profile.id
    )
    return DocumentList(
        documents=await _reads(db, docs), can_upload=True, can_delete=access.delete_documents
    )


@router.post(
    "/{user_id}/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    user_id: uuid.UUID,
    doc_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    """Upload a PDF, JPEG or PNG (up to 10 MB); it's encrypted before storage."""
    if not sensitive_access(perms, current_user.id, user_id).documents:
        raise forbid(NO_ACCESS)
    profile, _user = await load_record(db, current_user.org_id, user_id)
    data = await file.read(MAX_DOCUMENT_BYTES + 1)  # never read more than the cap
    subject = Subject(org_id=current_user.org_id, user_id=user_id, profile=profile)
    try:
        doc = await documents.upload(
            db,
            subject,
            current_user.id,
            doc_type=doc_type,
            filename=file.filename or "document",
            data=data,
        )
    except UploadPolicyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    try:
        await db.commit()
    except Exception:
        await documents.discard_blob(doc.storage_path)
        raise
    return (await _reads(db, [doc]))[0]


async def _document(
    db: AsyncSession, current_user: User, perms: PermissionSet, doc_id: uuid.UUID
) -> tuple[EmployeeDocument, Subject]:
    """The document and whose it is, or 404 / 403. "Whose" comes from the row."""
    doc = await EmployeeDocumentRepository(db, org_id=current_user.org_id).get_by_id(doc_id)
    profile = (
        await EmployeeProfileRepository(db, org_id=current_user.org_id).get_by_id(doc.profile_id)
        if doc
        else None
    )
    if doc is None or profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if not sensitive_access(perms, current_user.id, profile.user_id).documents:
        raise forbid(NO_ACCESS)
    return doc, Subject(org_id=current_user.org_id, user_id=profile.user_id, profile=profile)


@router.get("/documents/{doc_id}/content")
async def open_document(
    doc_id: uuid.UUID,
    download: bool = Query(False),
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The decrypted file; the view is logged."""
    doc, subject = await _document(db, current_user, perms, doc_id)
    opened = await documents.open_document(db, subject, current_user.id, doc)
    # The view must be on record before the file leaves the server.
    await db.commit()
    disposition = "attachment" if download else "inline"
    return Response(
        content=opened.data,
        media_type=opened.mime_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(opened.filename)}",
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            # Rendered inline, a file can't run scripts or reach the app.
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document (HR only); the deletion is logged."""
    doc, subject = await _document(db, current_user, perms, doc_id)
    if not sensitive_access(perms, current_user.id, subject.user_id).delete_documents:
        raise forbid("Only HR can delete documents.")
    path = await documents.delete_document(db, subject, current_user.id, doc)
    await db.commit()
    await documents.discard_blob(path)
