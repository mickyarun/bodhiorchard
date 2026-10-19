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

"""An employee's document (ID proof, offer letter, …), stored encrypted.

The file bytes are encrypted before they reach storage, at
``<org>/hr-documents/<profile>/<id>.bin``; the original filename is
encrypted too, since names like "aadhaar-ravi.pdf" say a lot on their own.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DocumentType(StrEnum):
    """What a document is, for sorting and labels."""

    ID_PROOF = "id_proof"
    ADDRESS_PROOF = "address_proof"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    OFFER_LETTER = "offer_letter"
    PAYSLIP = "payslip"
    OTHER = "other"


class EmployeeDocument(BaseModel):
    """One uploaded file."""

    __tablename__ = "employee_documents"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(
            DocumentType,
            name="employee_document_type",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    filename: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
