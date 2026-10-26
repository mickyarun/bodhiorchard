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

"""Delivery rules for the celebration poster: claim, retry, never double-post.

The DB and Slack are replaced with in-memory fakes so each rule in the
``poster`` module docstring is exercised directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.celebration_post import CelebrationPostStatus
from app.repositories.employee_profile import Celebrant
from app.schemas.settings import CelebrationSettings
from app.services.celebrations import poster
from app.services.celebrations.schedule import PostWindow
from app.services.slack_client import PostOutcome

ORG = uuid.uuid4()
TODAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 9, 45, tzinfo=UTC)
WINDOW = PostWindow(post_date=TODAY, occasions=(TODAY,), post_at=NOW)
SETTINGS = CelebrationSettings(
    enabled=True, slack_channel_id="C123", timezone="Europe/London", gif_enabled=False
)


def _sid() -> Celebrant:
    return Celebrant(
        user_id=uuid.uuid4(), name="Sid", avatar_url=None, slack_id="U1", month=10, day=22
    )


@dataclass
class _Row:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: CelebrationPostStatus = CelebrationPostStatus.FAILED
    attempts: int = 1
    covered_dates: list[date] = field(default_factory=lambda: [TODAY])
    updated_at: datetime = NOW - timedelta(minutes=30)


@dataclass
class _World:
    """Shared state every fake reads and writes."""

    existing: _Row | None = None
    announced_elsewhere: set[date] = field(default_factory=set)
    birthdays: list[Celebrant] = field(default_factory=lambda: [_sid()])
    token: str | None = "enc-token"
    claim_raises: bool = False
    retry_wins: bool = True
    outcomes: list[PostOutcome] = field(default_factory=lambda: [PostOutcome(ok=True, ts="1.2")])
    # observations
    claims: list[dict[str, Any]] = field(default_factory=list)
    retries: int = 0
    recorded: list[dict[str, Any]] = field(default_factory=list)
    sends: list[dict[str, Any]] = field(default_factory=list)
    celebrant_queries: list[list[date]] = field(default_factory=list)


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> _World:
    w = _World()

    class _Ledger:
        def __init__(self, db: Any, *, org_id: uuid.UUID) -> None:
            pass

        async def get_for_date(self, d: date) -> _Row | None:
            return w.existing

        async def dates_announced_near(self, d: date, *, span_days: int) -> set[date]:
            return set(w.announced_elsewhere)

        async def claim(self, d: date, **kw: Any) -> _Row:
            if w.claim_raises:
                raise IntegrityError("insert", {}, Exception("dup"))
            w.claims.append({"date": d, **kw})
            return _Row(status=CelebrationPostStatus.CLAIMED)

        async def claim_retry(self, row: _Row, *, slack_channel_id: str) -> bool:
            w.retries += 1
            return w.retry_wins

        async def record_outcome(self, row_id: uuid.UUID, **kw: Any) -> None:
            w.recorded.append(kw)

    class _Profiles:
        def __init__(self, db: Any, *, org_id: uuid.UUID) -> None:
            pass

        async def list_celebrants(self, occasions: Any, **kw: Any) -> tuple[list, list]:
            w.celebrant_queries.append(list(occasions))
            return (w.birthdays if occasions else []), []

    class _Orgs:
        def __init__(self, db: Any) -> None:
            pass

        async def get_slack_bot_token(self, org_id: uuid.UUID) -> str | None:
            return w.token

    async def _send(token: str, channel: str, text: str, *, blocks: Any = None) -> PostOutcome:
        w.sends.append({"channel": channel, "blocks": blocks})
        return w.outcomes.pop(0)

    async def _no_gif(**kw: Any) -> None:
        return None

    monkeypatch.setattr(poster, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(poster, "CelebrationPostRepository", _Ledger)
    monkeypatch.setattr(poster, "EmployeeProfileRepository", _Profiles)
    monkeypatch.setattr(poster, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(poster, "decrypt_secret", lambda s: "xoxb-plain")
    monkeypatch.setattr(poster, "post_message_outcome", _send)

    async def _slot(org_id: Any) -> bool:
        return True

    monkeypatch.setattr(poster, "random_celebration_gif", _no_gif)
    # The cooldown has its own tests below; keep it out of the others.
    monkeypatch.setattr(poster, "_claim_sample_slot", _slot)
    return w


async def _post() -> poster.PostResult:
    return await poster.post_digest(ORG, SETTINGS, WINDOW, now_utc=NOW)


class TestFixableProblemsNeverClaimTheDay:
    async def test_missing_token_leaves_the_day_open(self, world: _World) -> None:
        world.token = None
        result = await _post()
        assert result.reason == "no_slack_token"
        assert world.claims == []

    async def test_connecting_slack_later_still_posts(self, world: _World) -> None:
        world.token = None
        await _post()
        world.token = "enc-token"
        result = await _post()
        assert result.posted
        assert len(world.claims) == 1

    async def test_undecryptable_token_leaves_the_day_open(
        self, world: _World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_: str) -> str:
            raise ValueError("bad key")

        monkeypatch.setattr(poster, "decrypt_secret", _boom)
        result = await _post()
        assert result.reason == "token_decrypt_failed"
        assert world.claims == []

    async def test_nobody_to_celebrate_leaves_the_day_open(self, world: _World) -> None:
        world.birthdays = []
        result = await _post()
        assert result.reason == "nobody"
        assert world.claims == []
        assert world.sends == []


class TestHappyPath:
    async def test_posts_and_records_sent(self, world: _World) -> None:
        result = await _post()
        assert result.posted and result.birthdays == 1
        assert world.recorded[-1]["status"] is CelebrationPostStatus.SENT
        assert world.recorded[-1]["message_ts"] == "1.2"

    async def test_claim_records_what_was_covered(self, world: _World) -> None:
        await _post()
        assert world.claims[0]["covered_dates"] == [TODAY]

    async def test_lost_race_does_not_send(self, world: _World) -> None:
        world.claim_raises = True
        result = await _post()
        assert result.reason == "already_posted"
        assert world.sends == []


class TestCoverageDeduplication:
    async def test_dates_announced_by_a_neighbour_are_skipped(self, world: _World) -> None:
        world.announced_elsewhere = {TODAY}
        result = await _post()
        # Only date was already announced → nothing left to celebrate.
        assert result.reason == "nobody"
        assert world.celebrant_queries == [[]]


class TestDeliveryFailures:
    async def test_definite_failure_is_marked_failed(self, world: _World) -> None:
        world.outcomes = [PostOutcome(ok=False, error="channel_not_found")]
        result = await _post()
        assert not result.posted
        assert result.reason == "slack:channel_not_found"
        assert world.recorded[-1]["status"] is CelebrationPostStatus.FAILED

    async def test_maybe_delivered_is_unknown_never_failed(self, world: _World) -> None:
        world.outcomes = [PostOutcome(ok=False, error="ReadTimeout", maybe_delivered=True)]
        await _post()
        assert world.recorded[-1]["status"] is CelebrationPostStatus.UNKNOWN

    async def test_rejected_blocks_retry_text_only(self, world: _World) -> None:
        world.outcomes = [
            PostOutcome(ok=False, error="invalid_blocks"),
            PostOutcome(ok=True, ts="9.9"),
        ]
        result = await _post()
        assert result.posted
        assert len(world.sends) == 2
        second = world.sends[1]["blocks"]
        assert not any(b.get("accessory") or b["type"] == "image" for b in second)


class TestRetries:
    async def test_failed_day_is_retried_after_the_delay(self, world: _World) -> None:
        world.existing = _Row(attempts=1, updated_at=NOW - timedelta(minutes=11))
        result = await _post()
        assert result.posted
        assert world.retries == 1
        assert world.claims == []

    async def test_retry_waits_for_the_delay(self, world: _World) -> None:
        world.existing = _Row(attempts=1, updated_at=NOW - timedelta(minutes=2))
        result = await _post()
        assert result.reason == "retry_pending"
        assert world.sends == []

    async def test_retries_are_bounded(self, world: _World) -> None:
        world.existing = _Row(attempts=poster.MAX_ATTEMPTS)
        result = await _post()
        assert result.reason == "retries_exhausted"
        assert world.sends == []

    async def test_retry_re_announces_the_original_coverage(self, world: _World) -> None:
        saturday = date(2026, 10, 24)
        world.existing = _Row(covered_dates=[saturday], updated_at=NOW - timedelta(hours=1))
        await _post()
        assert world.celebrant_queries == [[saturday]]

    async def test_lost_retry_race_does_not_send(self, world: _World) -> None:
        world.existing = _Row(updated_at=NOW - timedelta(hours=1))
        world.retry_wins = False
        result = await _post()
        assert result.reason == "already_posted"
        assert world.sends == []

    @pytest.mark.parametrize("status", [CelebrationPostStatus.SENT, CelebrationPostStatus.UNKNOWN])
    async def test_sent_or_unknown_is_never_retried(
        self, world: _World, status: CelebrationPostStatus
    ) -> None:
        world.existing = _Row(status=status, updated_at=NOW - timedelta(hours=1))
        result = await _post()
        assert result.reason == "already_posted"
        assert world.sends == []


class TestSample:
    async def test_sample_never_touches_the_ledger(self, world: _World) -> None:
        result = await poster.post_sample(
            ORG,
            SETTINGS,
            actor_name="Arun",
            actor_slack_id="UADMIN",
            actor_avatar_url=None,
            today=TODAY,
        )
        assert result.posted
        assert world.claims == [] and world.recorded == [] and world.retries == 0
        assert "This is a test post" in str(world.sends[0]["blocks"])

    async def test_sample_works_with_nobody_celebrating(self, world: _World) -> None:
        world.birthdays = []
        result = await poster.post_sample(
            ORG,
            SETTINGS,
            actor_name="Arun",
            actor_slack_id=None,
            actor_avatar_url=None,
            today=TODAY,
        )
        assert result.posted

    async def test_sample_reports_slack_errors(self, world: _World) -> None:
        world.outcomes = [PostOutcome(ok=False, error="not_in_channel")]
        result = await poster.post_sample(
            ORG,
            SETTINGS,
            actor_name="Arun",
            actor_slack_id=None,
            actor_avatar_url=None,
            today=TODAY,
        )
        assert result.reason == "slack:not_in_channel"
