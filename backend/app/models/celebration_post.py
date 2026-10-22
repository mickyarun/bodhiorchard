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

"""Ledger of celebration digests already posted to Slack.

One row per ``(org_id, celebrate_date)``. The daily scheduler ticks every
60s, so without a durable marker a backend restart inside the post window
would re-announce the same birthdays. The unique constraint — not the
in-Python check — is the real guard: two instances racing the same tick
both see "no row", and the loser's INSERT is rejected.

Mirrors the ``quizzes.exists_for_date`` idempotency used by the quiz
scheduler, with two additions the quiz does not need:

* ``status`` / ``attempts`` / ``last_error`` — a Slack call that *definitely*
  did not deliver (Slack answered ``ok: false``, or the connection never
  opened) is retried a bounded number of times the same day, instead of
  silently costing everyone their announcement. A call whose outcome is
  unknown (timed out after sending) is never retried: a duplicate
  ``@channel`` post is worse than a missing one.
* ``covered_dates`` — the calendar dates this post actually announced.
  Coverage is derived from the *current* settings, so without a record a
  weekend-policy or timezone change could announce a date twice or skip
  it; the poster subtracts dates already covered by recent posts.
"""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class CelebrationPostStatus(StrEnum):
    """Delivery state of one day's digest."""

    # Date reserved; the Slack call has not reported back yet.
    CLAIMED = "claimed"
    # Slack accepted the message.
    SENT = "sent"
    # Slack definitely did not deliver; eligible for a bounded retry.
    FAILED = "failed"
    # The request may or may not have landed (e.g. read timeout). Never
    # retried automatically — an operator checks the channel.
    UNKNOWN = "unknown"


class CelebrationPost(BaseModel):
    """A celebration digest that has been posted for one local date."""

    __tablename__ = "celebration_posts"
    __table_args__ = (
        UniqueConstraint("org_id", "celebrate_date", name="uq_celebration_posts_org_date"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # The org-local date the digest covers, not the instant it was sent.
    celebrate_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Slack channel + message timestamp, kept so a future feature (threaded
    # replies, reaction counts, deletion on opt-out) can find the message.
    # Nullable because the row is written BEFORE the Slack call — claiming
    # the date is what makes the post exactly-once.
    slack_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_message_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    birthday_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    anniversary_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[CelebrationPostStatus] = mapped_column(
        Enum(
            CelebrationPostStatus,
            name="celebration_post_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=CelebrationPostStatus.CLAIMED,
        server_default=CelebrationPostStatus.CLAIMED.value,
    )
    # Slack calls made for this date, including the first.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Slack's error code (``channel_not_found``, ``ratelimited`` …) or the
    # transport exception name from the most recent failed attempt.
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    covered_dates: Mapped[list[date]] = mapped_column(
        ARRAY(Date), nullable=False, default=list, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<CelebrationPost(org_id={self.org_id}, date={self.celebrate_date})>"
