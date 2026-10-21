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

"""Documents as the Documents tab lists them, with what the caller may do."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_document import EmployeeDocument
from app.repositories.user import UserRepository
from app.schemas.employee_sensitive import DocumentRead
from app.schemas.leave import PersonRef
from app.services.employees.documents import listed_filename
from app.services.employees.sensitive_access import SensitiveAccess


async def document_reads(
    db: AsyncSession, docs: list[EmployeeDocument], access: SensitiveAccess, actor_id: uuid.UUID
) -> list[DocumentRead]:
    """Names, uploaders and per-document delete rights; never contents."""
    names = await UserRepository(db).get_names_by_ids(
        {d.uploaded_by for d in docs if d.uploaded_by}
    )
    return [
        DocumentRead(
            id=d.id,
            doc_type=d.doc_type,
            filename=listed_filename(d),
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
            uploaded_by=PersonRef(user_id=d.uploaded_by, name=names.get(d.uploaded_by, "Someone"))
            if d.uploaded_by
            else None,
            created_at=d.created_at,
            can_delete=access.may_delete(actor_id, d.uploaded_by),
        )
        for d in docs
    ]
