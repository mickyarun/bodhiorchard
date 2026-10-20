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

"""Re-encrypting HR data under the newest key in ``HR_ENCRYPTION_KEYS``.

Add the new key at the front of the keyring (keeping the old one after
it), deploy, run this, then drop the old key. Anything already under the
current key is skipped, so it's safe to run again after an interruption.
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hr_crypto
from app.models.employee_document import EmployeeDocument
from app.repositories.hr_rotation import HRRotationRepository
from app.services.employees.document_policy import ENCRYPTED_BLOB_POLICY
from app.services.employees.documents import document_aad, document_path
from app.services.employees.sensitive_details import ENCRYPTED, field_aad
from app.services.file_storage import FileStorage, FileStorageError, get_file_storage


@dataclass
class RotationReport:
    """How much was re-encrypted, and what couldn't be (by id, for a re-run)."""

    fields: int = 0
    documents: int = 0
    failed: list[str] = field(default_factory=list)


def _reencrypt(blob: bytes, aad: str, ring: hr_crypto.Keyring) -> bytes | None:
    """The blob under the current key, or None if it already is."""
    if hr_crypto.key_id(blob) == ring.current:
        return None
    return hr_crypto.encrypt(hr_crypto.decrypt(blob, aad, ring), aad, ring)


async def rotate(db: AsyncSession, *, dry_run: bool) -> RotationReport:
    """Re-encrypt every field and document not under the current key."""
    ring = hr_crypto.keyring()
    repo = HRRotationRepository(db)
    report = RotationReport()
    for row in await repo.all_sensitive():
        for name in ENCRYPTED:
            blob = getattr(row, name)
            if blob is None:
                continue
            try:
                fresh = _reencrypt(blob, field_aad(row.org_id, row.profile_id, name), ring)
            except hr_crypto.HRDecryptionError as exc:
                report.failed.append(f"details {row.id} {name}: {exc}")
                continue
            if fresh is not None:
                report.fields += 1
                if not dry_run:
                    setattr(row, name, fresh)
    storage = get_file_storage()
    for doc in await repo.all_documents():
        # One unreadable or missing file mustn't stop the rest: report it,
        # with the reason (key ids at most, never key bytes).
        try:
            await _rotate_document(doc, storage, ring, report, dry_run=dry_run)
        except (hr_crypto.HRDecryptionError, FileStorageError) as exc:
            report.failed.append(f"document {doc.id}: {type(exc).__name__}: {exc}")
    if not dry_run:
        await db.commit()
    return report


async def _rotate_document(
    doc: EmployeeDocument,
    storage: FileStorage,
    ring: hr_crypto.Keyring,
    report: RotationReport,
    *,
    dry_run: bool,
) -> None:
    """Re-encrypt one document's file and name. The file goes first: if
    storing it fails, the name stays as it was and both still match."""
    filename = _reencrypt(doc.filename, document_aad(doc.org_id, doc.id, "name"), ring)
    content, _ = await storage.download(doc.storage_path)
    body = _reencrypt(content, document_aad(doc.org_id, doc.id, "content"), ring)
    if filename is None and body is None:
        return
    if not dry_run:
        if body is not None:
            await storage.upload(
                str(doc.org_id),
                document_path(doc),
                body,
                "application/octet-stream",
                policy=ENCRYPTED_BLOB_POLICY,
            )
        if filename is not None:
            doc.filename = filename
    report.documents += 1
