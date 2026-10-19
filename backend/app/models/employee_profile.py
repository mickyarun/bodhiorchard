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

"""Employee record for an org member: work details plus personal contact data.

One row per ``(org_id, user_id)``. Bank, ID and address data live in a
separate encrypted table so ordinary reads of this row never touch them.
Reporting managers are a separate many-to-many table
(:class:`app.models.employee_reporting_manager.EmployeeReportingManager`).
"""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


def _values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class EmploymentType(StrEnum):
    """Contract type."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"


class EmployeeStatus(StrEnum):
    """Where the employee is in their tenure."""

    ACTIVE = "active"
    ON_NOTICE = "on_notice"
    EXITED = "exited"


class Gender(StrEnum):
    """Self-described gender; optional."""

    FEMALE = "female"
    MALE = "male"
    NON_BINARY = "non_binary"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class BloodGroup(StrEnum):
    """ABO/Rh blood group, kept for emergencies."""

    A_POSITIVE = "a_positive"
    A_NEGATIVE = "a_negative"
    B_POSITIVE = "b_positive"
    B_NEGATIVE = "b_negative"
    AB_POSITIVE = "ab_positive"
    AB_NEGATIVE = "ab_negative"
    O_POSITIVE = "o_positive"
    O_NEGATIVE = "o_negative"


class EmployeeProfile(BaseModel):
    """HR record for one member of an org."""

    __tablename__ = "employee_profiles"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_employee_profiles_org_user"),
        # Codes are optional, but unique within an org once assigned.
        Index(
            "uq_employee_profiles_org_code",
            "org_id",
            "employee_code",
            unique=True,
            postgresql_where="employee_code IS NOT NULL",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # RESTRICT: an employee record outlives the account being deactivated.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # ── Work ──
    employee_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(150), nullable=True)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType, name="employment_type", values_callable=_values),
        nullable=False,
        default=EmploymentType.FULL_TIME,
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        Enum(EmployeeStatus, name="employee_status", values_callable=_values),
        nullable=False,
        default=EmployeeStatus.ACTIVE,
    )
    date_of_joining: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_of_exit: Mapped[date | None] = mapped_column(Date, nullable=True)
    # ISO 3166-1 alpha-2; picks the default leave policy later.
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    work_location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # NULL = the org's default leave policy.
    leave_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "leave_policies.id", ondelete="RESTRICT", name="fk_employee_profiles_leave_policy"
        ),
        nullable=True,
    )
    # When the current policy was assigned; new allocations start from here.
    leave_policy_assigned_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ── Personal ──
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[Gender | None] = mapped_column(
        Enum(Gender, name="employee_gender", values_callable=_values), nullable=True
    )
    blood_group: Mapped[BloodGroup | None] = mapped_column(
        Enum(BloodGroup, name="blood_group", values_callable=_values), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    personal_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_contact_relation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    def __repr__(self) -> str:
        return f"<EmployeeProfile(id={self.id}, user_id={self.user_id})>"
