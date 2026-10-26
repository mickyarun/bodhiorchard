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

"""Regression tests for the celebrations review findings.

Each test pins one defect found in review (architecture, QA or code review)
so it cannot quietly return.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.models.celebration_post import CelebrationPostStatus
from app.repositories.employee_profile import Celebrant
from app.schemas.settings import CelebrationSettings
from app.schemas.settings import CelebrationWeekendPolicy as Policy
from app.services.celebrations import gif, poster, scheduler
from app.services.celebrations.compose import compose_digest, fallback_text
from app.services.celebrations.schedule import compute_post_window
from app.services.slack_client import PostOutcome

ORG = uuid.uuid4()
LONDON = ZoneInfo("Europe/London")
EVERY_DAY = list(range(7))


def _person(name: str, slack: str | None = None) -> Celebrant:
    return Celebrant(
        user_id=uuid.uuid4(), name=name, avatar_url=None, slack_id=slack, month=10, day=22
    )


# ── schedule ────────────────────────────────────────────────────────────────


def test_late_post_time_keeps_its_window_past_midnight() -> None:
    """23:00 + 3h still fires at 00:30, and counts as the day it was for."""
    window = compute_post_window(
        now_utc=datetime(2026, 10, 21, 23, 30, tzinfo=UTC),  # 00:30 BST on the 22nd
        zone=LONDON,
        post_time="23:00",
        active_weekdays=EVERY_DAY,
        policy=Policy.ROLL_FORWARD,
    )
    assert window is not None
    assert window.post_date == date(2026, 10, 21)


def test_yesterdays_slot_respects_posting_days() -> None:
    # Sunday 23:00 slot, Mon-Fri schedule: nothing at 00:30 on Monday.
    window = compute_post_window(
        now_utc=datetime(2026, 10, 18, 23, 30, tzinfo=UTC),
        zone=LONDON,
        post_time="23:00",
        active_weekdays=[0, 1, 2, 3, 4],
        policy=Policy.ROLL_FORWARD,
    )
    assert window is None


def test_post_time_in_the_spring_forward_gap_still_fires() -> None:
    # 01:30 does not exist in London on 2026-03-29; the slot must still open.
    window = compute_post_window(
        now_utc=datetime(2026, 3, 29, 2, 0, tzinfo=UTC),
        zone=LONDON,
        post_time="01:30",
        active_weekdays=EVERY_DAY,
        policy=Policy.ROLL_FORWARD,
    )
    assert window is not None
    assert window.post_date == date(2026, 3, 29)


# ── compose ─────────────────────────────────────────────────────────────────


def test_overflow_ends_on_a_complete_mention() -> None:
    people = [_person(f"P{i}", slack=f"U{i:010d}") for i in range(400)]
    blocks = compose_digest(people, [])
    overflow = next(b for b in blocks if b.get("text", {}).get("text", "").startswith("…and"))
    text = overflow["text"]["text"]
    assert len(text) <= 3000
    assert text.count("<@") == text.count(">"), text[-40:]
    assert text.endswith(" …")


def test_fallback_text_names_each_person_once() -> None:
    sid = _person("Sid")
    text = fallback_text([sid], [sid, _person("Ana")])
    assert text == "Celebrating Sid, Ana today!"


# ── gif ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("payload", [{"data": []}, {"data": "x"}, ["not", "a", "dict"], {}])
async def test_odd_giphy_replies_never_raise(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    real = httpx.AsyncClient

    def _client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))

    monkeypatch.setattr(gif.httpx, "AsyncClient", _client)
    monkeypatch.setattr(gif.settings.integrations, "giphy_api_key", "k")
    assert await gif.random_celebration_gif(tags=["party"]) is None


# ── poster ──────────────────────────────────────────────────────────────────


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _Row:
    def __init__(self, status: CelebrationPostStatus, age: timedelta) -> None:
        self.id = uuid.uuid4()
        self.status = status
        self.attempts = 1
        self.covered_dates = [date(2026, 10, 22)]
        self.updated_at = datetime(2026, 10, 22, 9, 45, tzinfo=UTC) - age


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Fake ledger + collaborators; returns the shared state."""
    state: dict[str, Any] = {
        "rows": {},
        "recorded": [],
        "announced_near_span": None,
        "send": lambda: PostOutcome(ok=True, ts="1"),
    }

    class _Ledger:
        def __init__(self, db: Any, *, org_id: Any) -> None:
            pass

        async def get_for_date(self, d: date) -> Any:
            return state["rows"].get(d)

        async def dates_announced_near(self, d: date, *, span_days: int) -> set[date]:
            state["announced_near_span"] = span_days
            return set()

        async def claim(self, d: date, **kw: Any) -> Any:
            row = _Row(CelebrationPostStatus.CLAIMED, timedelta(0))
            state["rows"][d] = row
            return row

        async def claim_retry(self, row: Any, **kw: Any) -> bool:
            return True

        async def record_outcome(self, row_id: Any, **kw: Any) -> None:
            state["recorded"].append(kw)

    class _Profiles:
        def __init__(self, db: Any, *, org_id: Any) -> None:
            pass

        async def list_celebrants(self, occasions: Any, **kw: Any) -> Any:
            return ([_person("A")] if occasions else []), []

    class _Orgs:
        def __init__(self, db: Any) -> None:
            pass

        async def get_slack_bot_token(self, org_id: Any) -> str:
            return "enc"

    async def _post(*a: Any, **kw: Any) -> PostOutcome:
        result = state["send"]()
        if asyncio.iscoroutine(result):
            return await result
        return result  # type: ignore[no-any-return]

    async def _no_gif(**kw: Any) -> None:
        return None

    monkeypatch.setattr(poster, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(poster, "CelebrationPostRepository", _Ledger)
    monkeypatch.setattr(poster, "EmployeeProfileRepository", _Profiles)
    monkeypatch.setattr(poster, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(poster, "decrypt_secret", lambda s: "xoxb")
    monkeypatch.setattr(poster, "post_message_outcome", _post)
    monkeypatch.setattr(poster, "random_celebration_gif", _no_gif)
    return state


SETTINGS = CelebrationSettings(
    enabled=True, slack_channel_id="C1", timezone="Europe/London", gif_enabled=False
)
NOW = datetime(2026, 10, 22, 9, 45, tzinfo=UTC)


def _window(day: date = date(2026, 10, 22)) -> Any:
    from app.services.celebrations.schedule import PostWindow

    return PostWindow(post_date=day, occasions=(day,), post_at=NOW)


async def test_an_interrupted_claim_becomes_unknown_not_stuck(ledger: dict[str, Any]) -> None:
    ledger["rows"][date(2026, 10, 22)] = _Row(
        CelebrationPostStatus.CLAIMED, poster.STALE_CLAIM + timedelta(minutes=1)
    )
    result = await poster.post_digest(ORG, SETTINGS, _window(), now_utc=NOW)
    assert result.reason == "interrupted"
    assert ledger["recorded"][-1]["status"] is CelebrationPostStatus.UNKNOWN


async def test_a_fresh_claim_is_left_alone(ledger: dict[str, Any]) -> None:
    ledger["rows"][date(2026, 10, 22)] = _Row(CelebrationPostStatus.CLAIMED, timedelta(minutes=2))
    result = await poster.post_digest(ORG, SETTINGS, _window(), now_utc=NOW)
    assert result.reason == "already_posted"
    assert ledger["recorded"] == []


async def test_cancellation_mid_send_records_unknown_and_propagates(
    ledger: dict[str, Any],
) -> None:
    async def _cancelled() -> PostOutcome:
        raise asyncio.CancelledError

    ledger["send"] = _cancelled
    with pytest.raises(asyncio.CancelledError):
        await poster.post_digest(ORG, SETTINGS, _window(), now_utc=NOW)
    assert ledger["recorded"][-1]["status"] is CelebrationPostStatus.UNKNOWN
    assert ledger["recorded"][-1]["error"] == "cancelled"


async def test_dedupe_looks_twice_the_span_away(ledger: dict[str, Any]) -> None:
    await poster.post_digest(ORG, SETTINGS, _window(), now_utc=NOW)
    assert ledger["announced_near_span"] == 2 * poster.MAX_SPAN_DAYS


async def test_policy_flip_on_a_sparse_schedule_never_double_announces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mondays only: roll-backward then roll-forward must not repeat a day."""
    rows: dict[date, list[date]] = {}
    queried: list[list[date]] = []

    class _Ledger:
        def __init__(self, db: Any, *, org_id: Any) -> None:
            pass

        async def get_for_date(self, d: date) -> Any:
            return None

        async def dates_announced_near(self, d: date, *, span_days: int) -> set[date]:
            return {
                x
                for cd, cov in rows.items()
                if cd != d and abs((cd - d).days) <= span_days
                for x in cov
            }

        async def claim(self, d: date, *, covered_dates: Any, **kw: Any) -> Any:
            rows[d] = list(covered_dates)
            return _Row(CelebrationPostStatus.CLAIMED, timedelta(0))

        async def record_outcome(self, *a: Any, **kw: Any) -> None:
            return None

    class _Profiles:
        def __init__(self, db: Any, *, org_id: Any) -> None:
            pass

        async def list_celebrants(self, occasions: Any, **kw: Any) -> Any:
            queried.append(sorted(occasions))
            return ([_person("A")] if occasions else []), []

    class _Orgs:
        def __init__(self, db: Any) -> None:
            pass

        async def get_slack_bot_token(self, org_id: Any) -> str:
            return "enc"

    async def _ok(*a: Any, **kw: Any) -> PostOutcome:
        return PostOutcome(ok=True, ts="1")

    async def _no_gif(**kw: Any) -> None:
        return None

    monkeypatch.setattr(poster, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(poster, "CelebrationPostRepository", _Ledger)
    monkeypatch.setattr(poster, "EmployeeProfileRepository", _Profiles)
    monkeypatch.setattr(poster, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(poster, "decrypt_secret", lambda s: "x")
    monkeypatch.setattr(poster, "post_message_outcome", _ok)
    monkeypatch.setattr(poster, "random_celebration_gif", _no_gif)

    utc = ZoneInfo("UTC")

    async def _run(day: date, policy: Policy) -> None:
        settings = CelebrationSettings(
            enabled=True,
            slack_channel_id="C1",
            timezone="UTC",
            active_weekdays=[0],
            weekend_policy=policy,
            gif_enabled=False,
        )
        when = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=10)
        window = compute_post_window(
            now_utc=when, zone=utc, post_time="09:30", active_weekdays=[0], policy=policy
        )
        assert window is not None
        await poster.post_digest(ORG, settings, window, now_utc=when)

    monday = date(2026, 10, 5)
    await _run(monday, Policy.ROLL_BACKWARD)  # covers Mon 5 .. Sun 11
    await _run(monday + timedelta(days=7), Policy.ROLL_FORWARD)  # would cover 6 .. 12
    first, second = queried
    assert not set(first) & set(second), sorted(set(first) & set(second))


async def test_missing_token_is_warned_once_a_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[str] = []

    class _Orgs:
        def __init__(self, db: Any) -> None:
            pass

        async def get_slack_bot_token(self, org_id: Any) -> None:
            return None

    monkeypatch.setattr(poster, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(poster, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(poster.logger, "warning", lambda event, **kw: warnings.append(event))
    monkeypatch.setattr(poster, "_warned_no_token", {})
    org = uuid.uuid4()
    for _ in range(5):
        assert await poster._resolve_token(org) == (None, "no_slack_token")
    assert warnings == ["celebration_no_slack_token"]


class _FakeRedis:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if nx and key in self.keys:
            return False
        self.keys.add(key)
        return True


async def test_sample_cooldown_uses_redis_across_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()

    async def _get() -> _FakeRedis:
        return redis

    monkeypatch.setattr(poster, "get_redis", _get)
    org = uuid.uuid4()
    assert await poster._claim_sample_slot(org) is True
    assert await poster._claim_sample_slot(org) is False
    assert await poster._claim_sample_slot(uuid.uuid4()) is True  # per org


async def test_sample_cooldown_falls_back_without_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _none() -> None:
        return None

    monkeypatch.setattr(poster, "get_redis", _none)
    monkeypatch.setattr(poster, "_last_sample", {})
    org = uuid.uuid4()
    assert await poster._claim_sample_slot(org) is True
    assert await poster._claim_sample_slot(org) is False


async def test_sample_reports_the_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _busy(org_id: Any) -> bool:
        return False

    monkeypatch.setattr(poster, "_claim_sample_slot", _busy)
    result = await poster.post_sample(
        ORG,
        SETTINGS,
        actor_name="A",
        actor_slack_id=None,
        actor_avatar_url=None,
        today=date(2026, 10, 22),
    )
    assert result.reason == "cooldown"


# ── scheduler ───────────────────────────────────────────────────────────────


async def test_one_broken_org_does_not_stop_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    good, bad = uuid.uuid4(), uuid.uuid4()
    posted: list[uuid.UUID] = []

    class _Orgs:
        def __init__(self, db: Any) -> None:
            pass

        async def list_all_ids(self) -> list[uuid.UUID]:
            return [bad, good]

        async def get_config(self, org_id: uuid.UUID) -> dict[str, Any]:
            if org_id == bad:
                raise RuntimeError("corrupt row")
            return {
                "celebrations": {
                    "enabled": True,
                    "slack_channel_id": "C1",
                    "timezone": "UTC",
                    "post_time": "00:00",
                }
            }

    async def _post(org_id: uuid.UUID, settings: Any, window: Any) -> None:
        posted.append(org_id)

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(scheduler, "post_digest", _post)
    # Fix the window so the outcome doesn't depend on the wall clock.
    monkeypatch.setattr(scheduler, "compute_post_window", lambda **kw: "window")
    monkeypatch.setattr(scheduler.logger, "warning", lambda *a, **kw: None)
    await scheduler.tick_once()
    # The broken org (listed first) failed; the healthy one still got its turn.
    assert posted == [good]
