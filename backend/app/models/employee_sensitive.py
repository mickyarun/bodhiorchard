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

"""An employee's sensitive details: addresses, IDs and bank account.

The values are AES-GCM ciphertext (:mod:`app.core.hr_crypto`), bound to
the org, the employee profile and the field. Only the last four characters are kept
in plain text, for the masked view ("•••• 4321"); bank name and IFSC are
not secret. Loaded only by the services that mask, reveal or update it,
so directory and profile reads never decrypt anything.
"""

import uuid

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class EmployeeSensitiveDetails(BaseModel):
    """One row per employee profile."""

    __tablename__ = "employee_sensitive_details"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    current_address: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    permanent_address: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    pan: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    pan_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    aadhaar: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    aadhaar_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    passport_number: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    passport_number_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    bank_account_number: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    bank_account_number_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(11), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
