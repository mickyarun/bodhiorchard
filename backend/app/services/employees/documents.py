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

"""Uploading, listing, opening and deleting employee documents.

Bytes and filename are encrypted before anything is stored, bound to the
document's id. Every upload, view and deletion is in the access log.
"""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hr_crypto
from app.models.employee_audit_event import EmployeeAuditAction
from app.models.employee_document import DocumentType, EmployeeDocument
from app.repositories.employee_sensitive import (
    EmployeeAuditRepository,
    EmployeeDocumentRepository,
)
from app.services.employees.document_policy import ENCRYPTED_BLOB_POLICY, check_document
from app.services.employees.sensitive_details import Subject
from app.services.file_storage import get_file_storage

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class OpenedDocument:
    """A decrypted document, ready to send."""

    data: bytes
    mime_type: str
    filename: str


def document_aad(org_id: uuid.UUID, doc_id: uuid.UUID, part: str) -> str:
    """Associated data binding a document's ``content`` or ``name`` to it."""
    return f"{org_id}|document|{doc_id}|{part}"


def document_path(doc: EmployeeDocument) -> str:
    """Where a document's bytes live, relative to its org's namespace."""
    return f"hr-documents/{doc.profile_id}/{doc.id}.bin"


def filename_of(doc: EmployeeDocument) -> str:
    """The original filename (decrypted)."""
    return hr_crypto.decrypt(doc.filename, document_aad(doc.org_id, doc.id, "name")).decode()


UNREADABLE_NAME = "(name can't be read)"


def listed_filename(doc: EmployeeDocument) -> str:
    """The filename for a list: one unreadable name mustn't hide the others."""
    try:
        return filename_of(doc)
    except hr_crypto.HRDecryptionError:
        logger.error("hr_document_name_unreadable", doc_id=str(doc.id))
        return UNREADABLE_NAME


async def upload(
    db: AsyncSession,
    subject: Subject,
    actor_id: uuid.UUID,
    *,
    doc_type: DocumentType,
    filename: str,
    data: bytes,
) -> EmployeeDocument:
    """Check, encrypt and store a document."""
    mime = check_document(filename, data)
    doc_id = uuid.uuid4()
    blob = hr_crypto.encrypt(data, document_aad(subject.org_id, doc_id, "content"))
    # Everything that can fail before the row is saved happens before the
    # file is stored, so a failure never leaves an orphaned file behind.
    encrypted_name = hr_crypto.encrypt(
        filename.encode(), document_aad(subject.org_id, doc_id, "name")
    )
    path = await get_file_storage().upload(
        str(subject.org_id),
        f"hr-documents/{subject.profile.id}/{doc_id}.bin",  # see document_path
        blob,
        "application/octet-stream",
        policy=ENCRYPTED_BLOB_POLICY,
    )
    doc = EmployeeDocument(
        id=doc_id,
        org_id=subject.org_id,
        profile_id=subject.profile.id,
        doc_type=doc_type,
        filename=encrypted_name,
        mime_type=mime,
        size_bytes=len(data),
        storage_path=path,
        uploaded_by=actor_id,
    )
    try:
        await EmployeeDocumentRepository(db, org_id=subject.org_id).create(doc)
        _log(db, subject, actor_id, EmployeeAuditAction.DOCUMENT_UPLOADED, doc_id)
    except Exception:
        # The row didn't save: don't leave the stored file behind.
        await discard_blob(path)
        raise
    return doc


async def open_document(
    db: AsyncSession, subject: Subject, actor_id: uuid.UUID, doc: EmployeeDocument
) -> OpenedDocument:
    """Fetch and decrypt a document; the view is logged."""
    blob, _ = await get_file_storage().download(doc.storage_path)
    data = hr_crypto.decrypt(blob, document_aad(doc.org_id, doc.id, "content"))
    _log(db, subject, actor_id, EmployeeAuditAction.DOCUMENT_VIEWED, doc.id)
    return OpenedDocument(data=data, mime_type=doc.mime_type, filename=filename_of(doc))


async def delete_document(
    db: AsyncSession, subject: Subject, actor_id: uuid.UUID, doc: EmployeeDocument
) -> str:
    """Remove the row and log it; returns the stored file's path.

    The caller commits, then calls :func:`discard_blob`: deleting the file
    before the commit would lose it if the commit failed.
    """
    await EmployeeDocumentRepository(db, org_id=subject.org_id).delete(doc)
    _log(db, subject, actor_id, EmployeeAuditAction.DOCUMENT_DELETED, doc.id)
    await db.flush()
    return doc.storage_path


async def discard_blob(path: str) -> None:
    """Best-effort removal of a stored file; a failure leaves an orphan, logged."""
    try:
        await get_file_storage().delete(path)
    except Exception:
        logger.warning("hr_document_blob_orphaned", path=path, exc_info=True)


def _log(
    db: AsyncSession,
    subject: Subject,
    actor_id: uuid.UUID,
    action: EmployeeAuditAction,
    doc_id: uuid.UUID,
) -> None:
    EmployeeAuditRepository(db, org_id=subject.org_id).record(
        actor_id=actor_id,
        subject_user_id=subject.user_id,
        profile_id=subject.profile.id,
        action=action,
        target=str(doc_id),
    )
