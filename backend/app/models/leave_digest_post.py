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

"""One row per org per local day for the daily who's-out post.

The unique (org, day) row is the claim: whichever scheduler tick inserts
it first posts, so a restart or a second instance never double-posts. A
failed post is retried a few times within the day's window.
"""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, Enum, ForeignKey, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DigestStatus(StrEnum):
    """Where the day's post got to."""

    CLAIMED = "claimed"
    POSTED = "posted"
    FAILED = "failed"
    # Everyone is in (or every policy has the day off): nothing to post.
    SKIPPED = "skipped"


class LeaveDigestPost(BaseModel):
    """The daily post for one org and one local date."""

    __tablename__ = "leave_digest_posts"
    __table_args__ = (
        UniqueConstraint("org_id", "local_date", name="uq_leave_digest_posts_org_date"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[DigestStatus] = mapped_column(
        Enum(
            DigestStatus,
            name="leave_digest_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    # Slack's error code from the last failed attempt (never message text).
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
