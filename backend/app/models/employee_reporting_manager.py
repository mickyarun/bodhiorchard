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

"""Reporting-manager links: an employee can report to several people.

Any one of an employee's managers may approve their leave; one link is
marked primary for display. At most one primary per employee is enforced
by a partial unique index.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class EmployeeReportingManager(BaseModel):
    """One employee → manager link."""

    __tablename__ = "employee_reporting_managers"
    __table_args__ = (
        UniqueConstraint("profile_id", "manager_user_id", name="uq_employee_manager_pair"),
        Index(
            "uq_employee_manager_primary",
            "profile_id",
            unique=True,
            postgresql_where="is_primary",
        ),
        Index("ix_employee_managers_manager", "org_id", "manager_user_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employee_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    manager_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return (
            f"<EmployeeReportingManager(profile_id={self.profile_id}, "
            f"manager_user_id={self.manager_user_id}, primary={self.is_primary})>"
        )
