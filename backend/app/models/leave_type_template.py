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

"""An org-wide leave type that policies add from the library.

Each policy still gets its own ``leave_types`` row (requests, the ledger and
frozen allocations point at it, so balances stay per policy). A linked row
copies every rule from its library entry; only the yearly quota can differ
per policy. Editing the entry rewrites the linked rows, each with its own
history event.
"""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.employee_profile import Gender
from app.models.leave_type import LeaveAccrual, enum_values


class LeaveTypeTemplate(BaseModel):
    """A library leave type: the rules every linked policy type shares."""

    __tablename__ = "leave_type_templates"
    __table_args__ = (UniqueConstraint("org_id", "code", name="uq_leave_type_templates_org_code"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    # The default yearly quota; a policy may set its own. NULL = no limit.
    annual_quota_days: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    counts_toward_warning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_encashable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    accrual: Mapped[LeaveAccrual] = mapped_column(
        Enum(LeaveAccrual, name="leave_accrual", values_callable=enum_values, create_type=False),
        nullable=False,
        default=LeaveAccrual.UPFRONT,
        server_default=LeaveAccrual.UPFRONT.value,
    )
    eligible_genders: Mapped[list[Gender] | None] = mapped_column(
        ARRAY(
            Enum(Gender, name="employee_gender", values_callable=enum_values, create_type=False)
        ),
        nullable=True,
    )
    auto_approve: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    monthly_limit_days: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)
    stops_at_balance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    color_key: Mapped[str] = mapped_column(String(20), nullable=False, default="swatch-1")

    def __repr__(self) -> str:
        return f"<LeaveTypeTemplate(id={self.id}, code={self.code!r})>"
