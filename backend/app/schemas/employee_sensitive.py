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

"""DTOs for sensitive details, documents and the access log.

Reads are always masked; the only way to see a value is the reveal
endpoint, which returns one field and writes an access-log entry.
"""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.models.employee_audit_event import EmployeeAuditAction
from app.models.employee_document import DocumentType
from app.schemas.leave import PersonRef

SensitiveField = Literal[
    "current_address",
    "permanent_address",
    "pan",
    "aadhaar",
    "passport_number",
    "bank_account_number",
]

_FORMATS: dict[str, tuple[re.Pattern[str], str]] = {
    "pan": (re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]"), "PAN looks like ABCDE1234F."),
    "aadhaar": (re.compile(r"[0-9]{12}"), "Aadhaar is 12 digits."),
    "passport_number": (re.compile(r"[A-Z0-9]{6,9}"), "Passport numbers are 6–9 letters/digits."),
    "bank_account_number": (re.compile(r"[0-9]{6,20}"), "Account numbers are 6–20 digits."),
    "bank_ifsc": (re.compile(r"[A-Z]{4}0[A-Z0-9]{6}"), "IFSC looks like HDFC0001234."),
}


class SensitiveWrite(BaseModel):
    """Change some details. Omitted fields stay as they are; "" clears one."""

    current_address: str | None = Field(None, max_length=500)
    permanent_address: str | None = Field(None, max_length=500)
    pan: str | None = None
    aadhaar: str | None = None
    passport_number: str | None = None
    bank_account_number: str | None = None
    bank_name: str | None = Field(None, max_length=120)
    bank_ifsc: str | None = None

    @field_validator("pan", "aadhaar", "passport_number", "bank_account_number", "bank_ifsc")
    @classmethod
    def _format(cls, value: str | None, info: ValidationInfo) -> str | None:
        if not value:
            return value
        cleaned = re.sub(r"[\s-]", "", value).upper()
        pattern, message = _FORMATS[str(info.field_name)]
        if not pattern.fullmatch(cleaned):
            raise ValueError(message)
        return cleaned


class MaskedValue(BaseModel):
    """Whether a value is saved, and its last four characters when it's an ID."""

    is_set: bool
    last4: str | None = None


class SensitiveRead(BaseModel):
    """Masked details for the Bank & IDs tab."""

    current_address: MaskedValue
    permanent_address: MaskedValue
    pan: MaskedValue
    aadhaar: MaskedValue
    passport_number: MaskedValue
    bank_account_number: MaskedValue
    bank_name: str | None
    bank_ifsc: str | None
    updated_at: datetime | None
    can_edit: bool
    can_reveal: bool


class RevealRequest(BaseModel):
    """Which one field to show."""

    field: SensitiveField


class RevealResponse(BaseModel):
    """One plaintext value (None when it isn't set)."""

    field: SensitiveField
    value: str | None


class DocumentRead(BaseModel):
    """A document as listed (never its contents)."""

    id: uuid.UUID
    doc_type: DocumentType
    filename: str
    mime_type: str
    size_bytes: int
    uploaded_by: PersonRef | None
    created_at: datetime


class DocumentList(BaseModel):
    """A person's documents and what the caller may do with them."""

    documents: list[DocumentRead]
    can_upload: bool
    can_delete: bool
    # The size cap, so the upload dialog can say it and check before sending.
    max_upload_bytes: int


class AccessLogEntry(BaseModel):
    """One look at or change to someone's sensitive details or documents."""

    action: EmployeeAuditAction
    actor: PersonRef
    target: str
    at: datetime
