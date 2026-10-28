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

"""The celebration digest posts once per day against the real ledger.

The poster's rules are unit-tested with a fake ledger; this runs two
schedulers at once on real Postgres, with Slack and Giphy replaced, so the
ledger's uniqueness is what stops a second post.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import select, update

from app.models.celebration_post import CelebrationPost, CelebrationPostStatus
from app.models.employee_profile import EmployeeProfile
from app.schemas.settings import CelebrationSettings
from app.services.celebrations import poster
from app.services.celebrations.poster import post_digest
from app.services.celebrations.schedule import PostWindow
from app.services.slack_client import PostOutcome
from tests.integration.leave_support import Factory, setup_org

pytestmark = pytest.mark.integration

DAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 4, 0, tzinfo=UTC)
WINDOW = PostWindow(post_date=DAY, occasions=(DAY,), post_at=NOW)
SETTINGS = CelebrationSettings(enabled=True, slack_channel_id="C123", timezone="UTC")


@pytest.fixture
def slack(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> list[str]:
    """Route the poster to the test DB and record every Slack post it makes."""
    sent: list[str] = []

    async def _post(token: str, channel: str, text: str, **_: Any) -> PostOutcome:
        await asyncio.sleep(0)
        sent.append(text)
        return PostOutcome(ok=True, ts="1.0")

    async def _token(org_id: uuid.UUID) -> tuple[str | None, str | None]:
        return "xoxb-test", None

    async def _gif(**_: Any) -> None:
        return None

    monkeypatch.setattr(poster, "AsyncSessionLocal", pg_session_factory)
    monkeypatch.setattr(poster, "post_message_outcome", _post)
    monkeypatch.setattr(poster, "_resolve_token", _token)
    monkeypatch.setattr(poster, "random_celebration_gif", _gif)
    return sent


async def _org_with_birthday(factory: Factory) -> uuid.UUID:
    org, (person,), _ = await setup_org(factory, "Birthday")
    async with factory() as db:
        await db.execute(
            update(EmployeeProfile)
            .where(EmployeeProfile.user_id == person)
            .values(date_of_birth=date(1990, 10, 22))
        )
        await db.commit()
    return org


async def _ledger(factory: Factory, org: uuid.UUID) -> list[CelebrationPost]:
    async with factory() as db:
        stmt = select(CelebrationPost).where(CelebrationPost.org_id == org)
        return list((await db.execute(stmt)).scalars().all())


async def test_two_schedulers_at_once_post_a_single_digest(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    """Concurrent ticks for the same day send once; the loser reports already_posted."""
    org = await _org_with_birthday(pg_session_factory)
    results = await asyncio.gather(
        post_digest(org, SETTINGS, WINDOW, now_utc=NOW),
        post_digest(org, SETTINGS, WINDOW, now_utc=NOW),
    )
    assert sorted(r.posted for r in results) == [False, True]
    assert [r.reason for r in results if not r.posted] == ["already_posted"]
    assert len(slack) == 1 and "Birthday" in slack[0]
    (row,) = await _ledger(pg_session_factory, org)
    assert (row.status, row.celebrate_date, row.birthday_count, row.attempts) == (
        CelebrationPostStatus.SENT,
        DAY,
        1,
        1,
    )


async def test_a_later_tick_the_same_day_does_not_repost(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    """Once sent, every later tick for the day is a no-op."""
    org = await _org_with_birthday(pg_session_factory)
    first = await post_digest(org, SETTINGS, WINDOW, now_utc=NOW)
    again = await post_digest(org, SETTINGS, WINDOW, now_utc=NOW)
    assert first.posted and (again.posted, again.reason) == (False, "already_posted")
    assert len(slack) == 1
    assert len(await _ledger(pg_session_factory, org)) == 1


async def test_one_orgs_post_does_not_block_another(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    """The once-a-day key is per org: two orgs on the same day both post."""
    first = await _org_with_birthday(pg_session_factory)
    second = await _org_with_birthday(pg_session_factory)
    results = [await post_digest(org, SETTINGS, WINDOW, now_utc=NOW) for org in (first, second)]
    assert [r.posted for r in results] == [True, True] and len(slack) == 2


async def test_nobody_to_celebrate_leaves_the_day_unclaimed(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    """Without a celebrant nothing is sent and no ledger row blocks a later post."""
    org, _, _ = await setup_org(pg_session_factory, "NoBirthday")
    result = await post_digest(org, SETTINGS, WINDOW, now_utc=NOW)
    assert (result.posted, result.reason) == (False, "nobody")
    assert slack == [] and await _ledger(pg_session_factory, org) == []
