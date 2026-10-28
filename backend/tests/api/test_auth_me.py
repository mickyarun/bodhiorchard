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

"""``GET /auth/me`` carries the signed-in member's profile photo."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.v1 import auth as routes
from app.models.user import UserRole


def _me(avatar_url: str | None) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="asha@example.com",
        name="Asha Rao",
        role=UserRole.DEVELOPER,
        role_ref=None,
        slack_id=None,
        github_username=None,
        character_model=None,
        avatar_url=avatar_url,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def _no_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _perms(user: Any, db: Any) -> set[str]:
        return set()

    monkeypatch.setattr(routes, "get_user_permissions", _perms)


@pytest.mark.parametrize(
    "stored",
    [
        pytest.param("/api/v1/employees/avatars/0123456789abcdef0123456789abcdef", id="uploaded"),
        pytest.param("https://avatars.slack-edge.com/asha_512.png", id="from-slack"),
        pytest.param(None, id="none"),
    ],
)
async def test_me_returns_the_stored_photo(stored: str | None) -> None:
    result = await routes.get_me(current_user=_me(stored), db=None)  # type: ignore[arg-type]
    assert result.avatar_url == stored
