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

SAVED = {
    "enabled": True,
    "slack_channel_id": "CSAVED",
    "post_time": "09:30",
    "mention_channel": False,
}

HR = {"employees:manage"}
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

    monkeypatch.setattr(routes, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(routes, "EmployeeProfileRepository", _Profiles)
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
        "/api/v1/settings/celebrations/test",
    }
    routes_found = [r for r in api_router.routes if getattr(r, "path", "") in paths]
    assert len(routes_found) == 4  # GET + PATCH share a path
    for route in routes_found:
        required: set[str] = set()
        for dep in route.dependencies:  # type: ignore[attr-defined]
            required.update(getattr(dep.dependency, "required_permissions", ()))
        assert required == {"employees:manage", "org:edit_settings"}, route.path
