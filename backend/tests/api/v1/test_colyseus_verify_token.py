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

"""Handler tests for the bridge-only room-join token check.

The multiplayer server takes a joining player's user id, org and display
name from this endpoint alone, so it must answer with the stored name (the
JWT carries none) and refuse a token whose org is not exactly the room's.
Handler-with-fakes pattern, as in ``test_minigame_results.py``.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1 import internal_colyseus as mod

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    claims: dict[str, Any] | None,
    active: bool = True,
    engineering: bool = True,
    must_change_password: bool = False,
) -> None:
    monkeypatch.setattr(mod, "verify_token", MagicMock(return_value=claims))
    user = SimpleNamespace(
        id=USER_ID,
        name="Alice Stored",
        is_active=active,
        must_change_password=must_change_password,
    )
    repo = MagicMock(get_by_id=AsyncMock(return_value=user))
    monkeypatch.setattr(mod, "UserRepository", MagicMock(return_value=repo))
    monkeypatch.setattr(mod, "member_has_permission", AsyncMock(return_value=engineering))


async def _verify(org_id: object = ORG_ID) -> dict[str, Any]:
    payload = {"token": "jwt", "org_id": str(org_id) if org_id else org_id}
    return await mod.verify_user_token(payload, None, MagicMock())


async def test_answers_with_the_stored_display_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, claims={"sub": str(USER_ID), "org_id": str(ORG_ID)})

    assert await _verify() == {
        "valid": True,
        "user_id": str(USER_ID),
        "org_id": str(ORG_ID),
        "name": "Alice Stored",
    }


async def test_refuses_a_token_for_another_org(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, claims={"sub": str(USER_ID), "org_id": str(ORG_ID)})

    assert await _verify(uuid.uuid4()) == {"valid": False}


async def test_refuses_when_no_room_org_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, claims={"sub": str(USER_ID), "org_id": str(ORG_ID)})

    assert await _verify(None) == {"valid": False}
    assert await _verify("") == {"valid": False}


async def test_refuses_a_token_without_an_org(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, claims={"sub": str(USER_ID)})

    assert await _verify() == {"valid": False}


async def test_refuses_a_deactivated_member(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, claims={"sub": str(USER_ID), "org_id": str(ORG_ID)}, active=False)

    assert await _verify() == {"valid": False}


async def test_refuses_a_member_without_engineering_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, claims={"sub": str(USER_ID), "org_id": str(ORG_ID)}, engineering=False)

    assert await _verify() == {"valid": False}


async def test_refuses_a_member_who_must_change_their_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rest of the API refuses them until they change it, so the rooms do too."""
    _patch(
        monkeypatch,
        claims={"sub": str(USER_ID), "org_id": str(ORG_ID)},
        must_change_password=True,
    )

    assert await _verify() == {"valid": False}
