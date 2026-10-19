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

"""Masking, revealing and changing an employee's sensitive details.

Every value is encrypted with associated data ``org|profile|field``, so a
ciphertext moved to another person or field won't decrypt. It's bound to
the employee profile rather than the user account because merging
duplicate accounts moves the profile to the surviving user. Reveals and
changes are written to the access log in the same transaction.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hr_crypto
from app.models.employee_audit_event import EmployeeAuditAction
from app.models.employee_profile import EmployeeProfile
from app.models.employee_sensitive import EmployeeSensitiveDetails
from app.repositories.employee_sensitive import (
    EmployeeAuditRepository,
    EmployeeSensitiveRepository,
)
from app.schemas.employee_sensitive import MaskedValue, SensitiveRead, SensitiveWrite

# Encrypted fields, and whether the last four characters are kept for masking.
ENCRYPTED: dict[str, bool] = {
    "current_address": False,
    "permanent_address": False,
    "pan": True,
    "aadhaar": True,
    "passport_number": True,
    "bank_account_number": True,
}
PLAIN = ("bank_name", "bank_ifsc")
# Changing these is the classic payroll-fraud move: the employee is alerted.
ALERT_ON = frozenset({"pan", "aadhaar", "passport_number", "bank_account_number", "bank_ifsc"})


@dataclass(frozen=True)
class Subject:
    """Whose details, as the crypto binding and the access log need them."""

    org_id: uuid.UUID
    user_id: uuid.UUID
    profile: EmployeeProfile


def field_aad(org_id: uuid.UUID, profile_id: uuid.UUID, field: str) -> str:
    """Associated data binding a value to its org, profile and field."""
    return f"{org_id}|{profile_id}|{field}"


def _aad(subject: Subject, field: str) -> str:
    return field_aad(subject.org_id, subject.profile.id, field)


def masked(
    row: EmployeeSensitiveDetails | None, *, can_edit: bool, can_reveal: bool
) -> SensitiveRead:
    """The details as anyone allowed to see them sees them: never the values."""

    def mask(field: str) -> MaskedValue:
        if row is None or getattr(row, field) is None:
            return MaskedValue(is_set=False)
        last4 = getattr(row, f"{field}_last4") if ENCRYPTED[field] else None
        return MaskedValue(is_set=True, last4=last4)

    return SensitiveRead(
        **{field: mask(field) for field in ENCRYPTED},
        bank_name=row.bank_name if row else None,
        bank_ifsc=row.bank_ifsc if row else None,
        updated_at=row.updated_at if row else None,
        can_edit=can_edit,
        can_reveal=can_reveal,
    )


async def update_details(
    db: AsyncSession, subject: Subject, actor_id: uuid.UUID, body: SensitiveWrite
) -> set[str]:
    """Apply the fields present in ``body``; returns the names that changed."""
    repo = EmployeeSensitiveRepository(db, org_id=subject.org_id)
    row = await repo.for_profile_or_new(subject.profile.id)
    changed: set[str] = set()
    for field in body.model_fields_set:
        value = getattr(body, field) or None
        if field in ENCRYPTED:
            blob = hr_crypto.encrypt(value.encode(), _aad(subject, field)) if value else None
            setattr(row, field, blob)
            if ENCRYPTED[field]:
                setattr(row, f"{field}_last4", value[-4:] if value else None)
            changed.add(field)
        elif field in PLAIN and getattr(row, field) != value:
            setattr(row, field, value)
            changed.add(field)
    if changed:
        row.updated_by = actor_id
        _log(db, subject, actor_id, EmployeeAuditAction.DETAILS_UPDATED, ",".join(sorted(changed)))
        await db.flush()
    return changed


async def reveal(
    db: AsyncSession, subject: Subject, actor_id: uuid.UUID, field: str
) -> str | None:
    """One decrypted value; the reveal is logged even when nothing is saved."""
    row = await EmployeeSensitiveRepository(db, org_id=subject.org_id).for_profile(
        subject.profile.id
    )
    _log(db, subject, actor_id, EmployeeAuditAction.FIELD_REVEALED, field)
    blob = getattr(row, field) if row else None
    return hr_crypto.decrypt(blob, _aad(subject, field)).decode() if blob else None


def _log(
    db: AsyncSession,
    subject: Subject,
    actor_id: uuid.UUID,
    action: EmployeeAuditAction,
    target: str,
) -> None:
    EmployeeAuditRepository(db, org_id=subject.org_id).record(
        actor_id=actor_id,
        subject_user_id=subject.user_id,
        profile_id=subject.profile.id,
        action=action,
        target=target,
    )
