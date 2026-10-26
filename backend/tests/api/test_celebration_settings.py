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

"""Celebration settings: HR tunes the schedule, admins/owner own the channel."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.router import api_router
from app.api.v1 import settings as routes
from app.models.organization import Organization
from app.schemas.settings import CelebrationSettings
from app.services.celebrations.poster import PostResult
from tests.api.route_walk import ServedRoute, served_routes

SAVED = {
    "enabled": True,
    "slack_channel_id": "CSAVED",
    "timezone": "Europe/London",
    "post_time": "09:30",
    "mention_channel": False,
}

HR = {"employees:manage"}
# Audit events the fake repository received, newest last.
AUDIT: list[dict[str, Any]] = []
ADMIN = {"org:edit_settings"}


@dataclass
class _Perms:
    granted: set[str] = field(default_factory=set)
    is_owner: bool = False

    def has(self, permission: str) -> bool:
        return self.is_owner or permission in self.granted


@dataclass
class _User:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "Admin"
    slack_id: str | None = "UADMIN"
    avatar_url: str | None = None


class _Db:
    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        return None


@pytest.fixture
def org(monkeypatch: pytest.MonkeyPatch) -> Organization:
    organization = Organization(id=uuid.uuid4(), name="Acme", config={"celebrations": SAVED})

    class _Orgs:
        def __init__(self, db: Any) -> None:
            pass

        async def get_for_user(self, user: Any) -> Organization:
            return organization

    class _Profiles:
        def __init__(self, db: Any, *, org_id: Any) -> None:
            pass

        async def count_celebration_audience(self) -> tuple[int, int]:
            return 3, 4

    class _Events:
        def __init__(self, db: Any, *, org_id: Any) -> None:
            pass

        async def append(self, **kw: Any) -> None:
            AUDIT.append(kw)

    AUDIT.clear()
    monkeypatch.setattr(routes, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(routes, "EmployeeProfileRepository", _Profiles)
    monkeypatch.setattr(routes, "CelebrationConfigEventRepository", _Events)
    return organization


def _body(**changes: Any) -> CelebrationSettings:
    return CelebrationSettings(**{**SAVED, **changes})


async def _patch(body: CelebrationSettings, perms: _Perms) -> CelebrationSettings:
    return await routes.update_celebration_config(
        body, current_user=_User(), perms=perms, db=_Db()
    )


class TestChannelControl:
    async def test_hr_can_change_the_schedule(self, org: Organization) -> None:
        result = await _patch(_body(post_time="10:15"), _Perms(HR))
        assert result.post_time == "10:15"

    async def test_hr_cannot_change_the_channel(self, org: Organization) -> None:
        with pytest.raises(HTTPException) as exc:
            await _patch(_body(slack_channel_id="COTHER"), _Perms(HR))
        assert exc.value.status_code == 403
        assert org.config["celebrations"]["slack_channel_id"] == "CSAVED"

    async def test_hr_cannot_turn_on_the_channel_ping(self, org: Organization) -> None:
        with pytest.raises(HTTPException) as exc:
            await _patch(_body(mention_channel=True), _Perms(HR))
        assert exc.value.status_code == 403

    async def test_admin_can_change_the_channel(self, org: Organization) -> None:
        result = await _patch(_body(slack_channel_id="COTHER"), _Perms(ADMIN))
        assert result.slack_channel_id == "COTHER"

    async def test_owner_can_change_the_channel(self, org: Organization) -> None:
        result = await _patch(
            _body(slack_channel_id="COTHER", mention_channel=True), _Perms(is_owner=True)
        )
        assert result.slack_channel_id == "COTHER"
        assert result.mention_channel


class TestSampleChannel:
    @pytest.fixture(autouse=True)
    def _fake_sample(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        sent: list[str] = []

        async def _post_sample(org_id: Any, settings: CelebrationSettings, **kw: Any) -> Any:
            sent.append(settings.slack_channel_id or "")
            return PostResult(posted=True)

        monkeypatch.setattr(routes, "post_sample", _post_sample)
        return sent

    async def _test(self, body: CelebrationSettings | None, perms: _Perms) -> Any:
        return await routes.send_celebration_test(
            body, current_user=_User(), perms=perms, db=_Db()
        )

    async def test_hr_can_sample_the_saved_channel(self, org: Organization) -> None:
        result = await self._test(_body(post_time="11:00"), _Perms(HR))
        assert result.posted

    async def test_hr_cannot_sample_another_channel(self, org: Organization) -> None:
        with pytest.raises(HTTPException) as exc:
            await self._test(_body(slack_channel_id="CELSEWHERE"), _Perms(HR))
        assert exc.value.status_code == 403

    async def test_admin_can_sample_a_channel_before_saving_it(
        self, org: Organization, _fake_sample: list[str]
    ) -> None:
        result = await self._test(_body(slack_channel_id="CNEW"), _Perms(ADMIN))
        assert result.posted
        assert _fake_sample == ["CNEW"]


def test_celebration_routes_are_open_to_hr_and_admins() -> None:
    paths = {
        "/api/v1/settings/celebrations",
        "/api/v1/settings/celebrations/audience",
        "/api/v1/settings/celebrations/history",
        "/api/v1/settings/celebrations/test",
    }
    found = [r for r in served_routes(api_router) if r.path in paths]
    # GET + PATCH share the settings path, so one more route than paths.
    assert len(found) == len(paths) + 1, sorted(r.path for r in found)
    for route in found:
        assert _required_permissions(route) == {"employees:manage", "org:edit_settings"}, (
            route.path
        )


def _required_permissions(route: ServedRoute) -> set[str]:
    """Every permission a route's dependency tree enforces."""
    found: set[str] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        found.update(getattr(dep.call, "required_permissions", ()))
        stack.extend(dep.dependencies)
    return found


class TestAuditTrail:
    async def test_switching_on_is_recorded_with_the_actor(self, org: Organization) -> None:
        org.config = {"celebrations": {**SAVED, "enabled": False}}
        await _patch(_body(), _Perms(ADMIN))
        assert AUDIT[-1]["action"].value == "enabled"
        assert AUDIT[-1]["changes"]["enabled"] == [False, True]

    async def test_channel_change_is_its_own_action(self, org: Organization) -> None:
        await _patch(_body(slack_channel_id="CNEW"), _Perms(ADMIN))
        assert AUDIT[-1]["action"].value == "channel_changed"
        assert AUDIT[-1]["changes"] == {"slack_channel_id": ["CSAVED", "CNEW"]}

    async def test_other_edits_are_updates(self, org: Organization) -> None:
        await _patch(_body(post_time="10:15"), _Perms(HR))
        assert AUDIT[-1]["action"].value == "updated"
        assert AUDIT[-1]["changes"] == {"post_time": ["09:30", "10:15"]}

    async def test_saving_unchanged_settings_records_nothing(self, org: Organization) -> None:
        await _patch(_body(), _Perms(HR))
        assert AUDIT == []


async def test_history_lists_each_days_outcome(
    org: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date
    from types import SimpleNamespace

    from app.models.celebration_post import CelebrationPostStatus

    rows = [
        SimpleNamespace(
            celebrate_date=date(2026, 10, 22),
            status=CelebrationPostStatus.FAILED,
            attempts=3,
            birthday_count=1,
            anniversary_count=0,
            last_error="not_in_channel",
        )
    ]

    class _Ledger:
        def __init__(self, db: Any, *, org_id: Any) -> None:
            pass

        async def list_recent(self, limit: int) -> list[Any]:
            return rows

    monkeypatch.setattr(routes, "CelebrationPostRepository", _Ledger)
    history = await routes.get_celebration_history(current_user=_User(), db=_Db())
    assert history[0].status == "failed"
    assert history[0].last_error == "not_in_channel"


def test_a_timezone_is_required_to_switch_on() -> None:
    with pytest.raises(ValueError, match="timezone"):
        CelebrationSettings(enabled=True, slack_channel_id="C1")
    # Allowed while off, so an unconfigured org still validates.
    assert CelebrationSettings(enabled=False).timezone is None
