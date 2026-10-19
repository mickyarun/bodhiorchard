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

"""An office people can work from, maintained by HR.

An office can name a leave policy: putting someone in the office moves
them onto it (HR can still choose another policy for a person).
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class OfficeLocation(BaseModel):
    """One office, e.g. "Chennai HQ"."""

    __tablename__ = "office_locations"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_office_locations_org_name"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ISO 3166-1 alpha-2.
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # The policy people in this office follow; kept null if it's deleted.
    leave_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "leave_policies.id", ondelete="SET NULL", name="fk_office_locations_leave_policy"
        ),
        nullable=True,
    )
