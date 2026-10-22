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

"""Slack member import/link never trust a photo URL sent by the client."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.api.v1 import settings_slack as routes
from app.services.avatars import SlackPhotoSync

ORG_ID = uuid.uuid4()


@dataclass
class _Org:
    id: uuid.UUID = ORG_ID
    slack_bot_token: str | None = "enc"


@dataclass
class _Caller:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    email: str = "admin@example.com"


class _Db:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"created": [], "sync_calls": [], "users": {}}

    class _Orgs:
        def __init__(self, db: Any) -> None:
            pass

        async def get_for_user(self, user: Any) -> _Org:
            return _Org()

    class _Users:
        def __init__(self, db: Any, org_id: Any = None) -> None:
            pass

        async def get_by_email_in_org(self, org_id: Any, email: str) -> None:
            return None

        async def create(self, user: Any) -> Any:
            user.id = uuid.uuid4()
            state["created"].append(user)
            return user

        async def get_by_id_with_membership(self, uid: uuid.UUID, org_id: Any) -> Any:
            return state["users"].get(uid)

    async def _sync(db: Any, **kw: Any) -> SlackPhotoSync:
        state["sync_calls"].append(kw)
        return SlackPhotoSync(
            updated=len(kw["only_user_ids"]), skipped_no_photo=0, skipped_has_photo=0
        )

    class _Identities:
        def __init__(self, db: Any) -> None:
            pass

        async def members_with_slack_id(self, org_id: Any, slack_id: str) -> list[Any]:
            return []

    async def _may_relink(db: Any, **kw: Any) -> None:
        return None

    monkeypatch.setattr(routes, "SlackIdentityRepository", _Identities)
    monkeypatch.setattr(routes, "assert_can_relink", _may_relink)
    monkeypatch.setattr(routes, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(routes, "UserRepository", _Users)
    monkeypatch.setattr(routes, "sync_slack_photos", _sync)
    monkeypatch.setattr(routes, "decrypt_secret", lambda s: "xoxb")
    return state


async def test_import_ignores_a_client_supplied_photo_url(env: dict[str, Any]) -> None:
    body = routes.SlackImportRequest.model_validate(
        {
            "imports": [
                {
                    "slack_id": "U1",
                    "slack_name": "Sid",
                    "slack_email": "sid@example.com",
                    # An older client — or a hostile one — still sends this.
                    "slack_avatar": "https://evil.example.com/track.png",
                }
            ]
        }
    )
    result = await routes.import_slack_members(body, current_user=_Caller(), db=_Db())

    assert result.imported == 1
    created = env["created"][0]
    assert created.avatar_url is None
    # The photo is fetched from Slack's API for exactly the new member.
    assert env["sync_calls"] == [
        {"org_id": ORG_ID, "bot_token": "xoxb", "only_user_ids": [created.id]}
    ]


async def test_import_survives_a_slack_photo_failure(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(db: Any, **kw: Any) -> SlackPhotoSync:
        raise RuntimeError("slack down")

    monkeypatch.setattr(routes, "sync_slack_photos", _boom)
    body = routes.SlackImportRequest.model_validate(
        {"imports": [{"slack_id": "U1", "slack_name": "Sid", "slack_email": "s@example.com"}]}
    )
    result = await routes.import_slack_members(body, current_user=_Caller(), db=_Db())
    assert result.imported == 1


async def test_link_fetches_photos_server_side(env: dict[str, Any]) -> None:
    @dataclass
    class _Member:
        id: uuid.UUID
        slack_id: str | None = None
        avatar_url: str | None = None

    member = _Member(id=uuid.uuid4())
    env["users"][member.id] = member
    body = routes.SlackLinkRequest(
        links=[
            {
                "slack_id": "U9",
                "user_id": str(member.id),
                "slack_avatar": "https://evil.example.com/x.png",
            }
        ]
    )
    result = await routes.link_slack_members(
        body, current_user=_Caller(), perms=object(), db=_Db()
    )

    assert result == {"linked": 1, "avatars": 1}
    assert member.slack_id == "U9"
    assert member.avatar_url is None  # only sync_slack_photos may set it
    assert env["sync_calls"][0]["only_user_ids"] == [member.id]
