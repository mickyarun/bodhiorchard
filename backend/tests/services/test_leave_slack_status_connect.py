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

from app.services.leave.slack_status import oauth
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

        async def save(self, user_id: uuid.UUID, slack_user_id: str, _token: str) -> None:
            rec.saved.append((user_id, slack_user_id))

    monkeypatch.setattr(oauth, "exchange_code", exchange)
    monkeypatch.setattr(oauth, "revoke", revoke)
    monkeypatch.setattr(oauth, "SlackStatusLinkRepository", Links)
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
    await complete(None, CLIENT, ORG, USER, "code")  # type: ignore[arg-type]
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
