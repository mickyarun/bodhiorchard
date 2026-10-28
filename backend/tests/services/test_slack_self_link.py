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

"""A member links their own Slack account only when it's provably theirs."""

import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.services import slack_self_link
from app.services.slack_self_link import link_own_account

ORG = uuid.uuid4()
SLACK_ID = "U_ME"


class FakeDb:
    def __init__(self) -> None:
        self.flushed = 0

    async def flush(self) -> None:
        self.flushed += 1


def _world(
    monkeypatch: pytest.MonkeyPatch,
    *,
    slack_user: dict[str, Any] | None | Exception,
    orgs: int = 1,
    holders: list[uuid.UUID] | None = None,
    token: str = "xoxb-1",
) -> None:
    class Identities:
        def __init__(self, *_a: Any) -> None:
            pass

        async def membership_count(self, _user_id: uuid.UUID) -> int:
            return orgs

        async def members_with_slack_id(self, _org: uuid.UUID, _slack: str) -> list[uuid.UUID]:
            return holders or []

    async def bot_token(*_a: Any) -> str:
        return token

    async def users_info(_token: str, slack_user_id: str) -> dict[str, Any] | None:
        assert slack_user_id == SLACK_ID
        if isinstance(slack_user, Exception):
            raise slack_user
        return slack_user

    monkeypatch.setattr(slack_self_link, "SlackIdentityRepository", Identities)
    monkeypatch.setattr(slack_self_link, "bot_token", bot_token)
    monkeypatch.setattr(slack_self_link, "users_info", users_info)


def _slack_user(email: str = "Asha@Example.com", **extra: Any) -> dict[str, Any]:
    return {"id": SLACK_ID, "profile": {"email": email}, **extra}


def _member(slack_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), email=" asha@example.com", slack_id=slack_id)


async def test_matching_email_links_the_account(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, slack_user=_slack_user())
    db, member = FakeDb(), _member()
    assert await link_own_account(db, ORG, member, SLACK_ID) is True  # type: ignore[arg-type]
    assert member.slack_id == SLACK_ID
    assert db.flushed == 1


@pytest.mark.parametrize(
    "world",
    [
        pytest.param({"slack_user": _slack_user("someone.else@example.com")}, id="other-email"),
        pytest.param({"slack_user": _slack_user("")}, id="no-email"),
        pytest.param({"slack_user": None}, id="bot-cannot-see-it"),
        pytest.param({"slack_user": httpx.ConnectError("down")}, id="slack-unreachable"),
        pytest.param({"slack_user": _slack_user(is_email_confirmed=False)}, id="unconfirmed"),
        pytest.param({"slack_user": _slack_user(deleted=True)}, id="deactivated"),
        pytest.param({"slack_user": _slack_user(is_bot=True)}, id="bot-account"),
        pytest.param({"slack_user": _slack_user(is_stranger=True)}, id="other-workspace"),
        pytest.param({"slack_user": _slack_user("asha@exämple.com")}, id="lookalike"),
        pytest.param({"slack_user": _slack_user(), "token": ""}, id="no-bot-token"),
        pytest.param({"slack_user": _slack_user(), "holders": [uuid.uuid4()]}, id="taken"),
        pytest.param({"slack_user": _slack_user(), "orgs": 2}, id="in-another-org"),
    ],
)
async def test_anything_unproven_is_refused(
    monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    _world(monkeypatch, **world)
    db, member = FakeDb(), _member()
    assert await link_own_account(db, ORG, member, SLACK_ID) is False  # type: ignore[arg-type]
    assert member.slack_id is None
    assert db.flushed == 0


async def test_an_existing_link_is_never_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, slack_user=_slack_user())
    db, member = FakeDb(), _member(slack_id="U_OLD")
    assert await link_own_account(db, ORG, member, SLACK_ID) is False  # type: ignore[arg-type]
    assert member.slack_id == "U_OLD"


SLACK_PHOTO = "https://avatars.slack-edge.com/me_512.png"


def _with_photo(**extra: Any) -> dict[str, Any]:
    user = _slack_user()
    user["profile"] |= {"is_custom_image": True, "image_512": SLACK_PHOTO, **extra}
    return user


def _member_with_photo(url: str | None, stored: str | None = None) -> SimpleNamespace:
    member = _member()
    member.avatar_url, member.avatar_storage_path = url, stored
    return member


async def test_linking_brings_in_the_slack_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, slack_user=_with_photo())
    member = _member_with_photo(None)
    assert await link_own_account(FakeDb(), ORG, member, SLACK_ID) is True  # type: ignore[arg-type]
    assert member.avatar_url == SLACK_PHOTO


async def test_linking_never_replaces_an_uploaded_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, slack_user=_with_photo())
    member = _member_with_photo("/api/v1/employees/avatars/abc", stored="org/avatars/abc.jpg")
    assert await link_own_account(FakeDb(), ORG, member, SLACK_ID) is True  # type: ignore[arg-type]
    assert member.avatar_url == "/api/v1/employees/avatars/abc"


async def test_slacks_generated_letter_tile_is_not_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _world(monkeypatch, slack_user=_with_photo(is_custom_image=False))
    member = _member_with_photo(None)
    assert await link_own_account(FakeDb(), ORG, member, SLACK_ID) is True  # type: ignore[arg-type]
    assert member.avatar_url is None


async def test_a_malformed_slack_profile_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, slack_user={"id": SLACK_ID, "profile": "not-a-profile"})
    member = _member_with_photo(None)
    assert await link_own_account(FakeDb(), ORG, member, SLACK_ID) is False  # type: ignore[arg-type]
    assert member.slack_id is None
