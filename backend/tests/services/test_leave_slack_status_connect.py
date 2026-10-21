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

"""Connecting Slack status: only the member's own linked Slack account is kept."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.encryption import encrypt_secret
from app.services import slack_user_api
from app.services.leave.slack_status import apply, oauth
from app.services.leave.slack_status.oauth import WrongSlackAccountError, complete
from app.services.leave.slack_status.settings import StatusClient
from app.services.slack_user_api import SlackUserApiError, UserGrant

ORG, USER = uuid.uuid4(), uuid.uuid4()
CLIENT = StatusClient(enabled=True, client_id="1.2", client_secret="s")


class Recorder:
    def __init__(self) -> None:
        self.saved: list[tuple[uuid.UUID, str]] = []
        self.revoked: list[str] = []


@pytest.fixture
def slack(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()

    async def exchange(*_args: Any) -> UserGrant:
        return UserGrant(slack_user_id="U_ME", token="xoxp-1", team_id="T1")

    async def revoke(token: str) -> None:
        rec.revoked.append(token)
        raise SlackUserApiError("token_revoked")  # a failing revoke mustn't hide the reason

    class Links:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def save(
            self, user_id: uuid.UUID, _team: str, slack_user_id: str, _token: str
        ) -> None:
            rec.saved.append((user_id, slack_user_id))

    monkeypatch.setattr(oauth, "exchange_code", exchange)
    monkeypatch.setattr(oauth, "revoke", revoke)

    class Accounts:
        def __init__(self, *_a: Any) -> None:
            pass

        async def links_elsewhere(self, *_a: Any) -> list[object]:
            return []

        async def remove_elsewhere(self, *_a: Any) -> int:
            return 0

    monkeypatch.setattr(oauth, "SlackStatusLinkRepository", Links)
    monkeypatch.setattr(oauth, "SlackStatusAccountRepository", Accounts)
    return rec


def _member(monkeypatch: pytest.MonkeyPatch, slack_id: str | None) -> None:
    class Users:
        def __init__(self, *_a: Any) -> None:
            pass

        async def get_by_id_in_org(self, *_a: Any) -> object:
            return SimpleNamespace(slack_id=slack_id)

    monkeypatch.setattr(oauth, "UserRepository", Users)


async def test_own_account_is_kept(slack: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    _member(monkeypatch, "U_ME")
    connected = await complete(None, CLIENT, ORG, USER, "code")  # type: ignore[arg-type]
    assert connected.moved is False
    assert connected.stale_tokens == []
    assert slack.saved == [(USER, "U_ME")]
    assert slack.revoked == []


@pytest.mark.parametrize("linked", ["U_COLLEAGUE", None])
async def test_another_account_is_refused_and_handed_back(
    slack: Recorder, monkeypatch: pytest.MonkeyPatch, linked: str | None
) -> None:
    _member(monkeypatch, linked)
    with pytest.raises(WrongSlackAccountError):
        await complete(None, CLIENT, ORG, USER, "code")  # type: ignore[arg-type]
    assert slack.saved == []
    assert slack.revoked == ["xoxp-1"]


class FakeLinks:
    removed: list[uuid.UUID] = []

    def __init__(self, *_a: Any, **_k: Any) -> None:
        pass

    async def remove(self, user_id: uuid.UUID) -> bool:
        FakeLinks.removed.append(user_id)
        return True


@pytest.mark.parametrize(
    ("reachable", "keep_to_retry", "dropped"),
    [
        (True, True, True),
        (False, True, False),  # someone who left: keep it, clear it next tick
        (False, False, True),  # an explicit disconnect: drop it anyway
    ],
)
async def test_forget_keeps_the_link_to_retry_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, reachable: bool, keep_to_retry: bool, dropped: bool
) -> None:
    FakeLinks.removed = []

    async def clear(*_a: Any) -> bool:
        return reachable

    monkeypatch.setattr(apply, "clear", clear)
    monkeypatch.setattr(apply, "SlackStatusLinkRepository", FakeLinks)
    link = SimpleNamespace(org_id=ORG, user_id=USER, token=encrypt_secret("xoxp-1"))
    token = await apply.forget(None, link, keep_to_retry=keep_to_retry)  # type: ignore[arg-type]
    assert (token == "xoxp-1") is dropped
    assert (FakeLinks.removed == [USER]) is dropped


async def test_enterprise_id_wins_over_the_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {
        "ok": True,
        "authed_user": {"id": "W1", "access_token": "xoxp-1"},
        "team": {"id": "T1"},
        "enterprise": {"id": "E1"},
    }

    class Client:
        def __init__(self, **_k: Any) -> None:
            pass

        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

        async def post(self, *_a: Any, **_k: Any) -> Any:
            return SimpleNamespace(json=lambda: body)

    monkeypatch.setattr(slack_user_api.httpx, "AsyncClient", Client)
    grant = await slack_user_api.exchange_code("id", "secret", "code", "https://cb")
    assert grant.team_id == "E1"
