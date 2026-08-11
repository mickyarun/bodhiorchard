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

"""Tests for ``identity_resolution.resolve_canonical_user``.

Covers the github-login happy path, the email/alias fallback that
recovers contributors with a blank ``github_username`` (the BUD-029
miss), and the both-miss → None contract.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.identity_resolution import resolve_canonical_user


def _db_returning(user: object | None) -> MagicMock:
    """A session stub whose ``get`` resolves to ``user``."""
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    return db


def _user(user_id: uuid.UUID, *, is_active: bool = True) -> MagicMock:
    """A user stub with the attributes the resolver touches."""
    user = MagicMock()
    user.id = user_id
    user.is_active = is_active
    return user


@pytest.mark.asyncio
async def test_github_login_resolves_first() -> None:
    user_id = uuid.uuid4()
    repo = MagicMock()
    repo.get_id_by_github_login = AsyncMock(return_value=user_id)

    with patch("app.services.identity_resolution.UserRepository", return_value=repo):
        resolved = await resolve_canonical_user(
            _db_returning(_user(user_id)),
            uuid.uuid4(),
            github_login="dev1",
            email="dev1@x.io",
        )

    assert resolved == user_id


@pytest.mark.asyncio
async def test_login_on_deactivated_row_walks_to_survivor() -> None:
    """A stale login on a merged-away row redirects to who absorbed it."""
    stale_id, target_id = uuid.uuid4(), uuid.uuid4()
    repo = MagicMock()
    repo.get_id_by_github_login = AsyncMock(return_value=stale_id)

    with (
        patch("app.services.identity_resolution.UserRepository", return_value=repo),
        patch(
            "app.services.identity_resolution.walk_to_active_user",
            new=AsyncMock(return_value=_user(target_id)),
        ),
    ):
        resolved = await resolve_canonical_user(
            _db_returning(_user(stale_id, is_active=False)),
            uuid.uuid4(),
            github_login="oldlogin",
        )

    assert resolved == target_id


@pytest.mark.asyncio
async def test_email_fallback_when_github_username_blank() -> None:
    """Login misses (no github_username) → email/alias recovers the user."""
    user_id = uuid.uuid4()
    repo = MagicMock()
    repo.get_id_by_github_login = AsyncMock(return_value=None)

    with (
        patch("app.services.identity_resolution.UserRepository", return_value=repo),
        patch(
            "app.services.identity_resolution.resolve_user_by_email",
            new=AsyncMock(return_value=_user(user_id)),
        ),
    ):
        resolved = await resolve_canonical_user(
            _db_returning(None), uuid.uuid4(), github_login="bala", email="bala@x.io"
        )

    assert resolved == user_id


@pytest.mark.asyncio
async def test_email_hit_on_deactivated_row_is_not_credited() -> None:
    """A merged-away stub keeps its primary email; it must not win.

    Without the alias walk the stub's own noreply address resolves back
    to the stub, re-stranding the attribution the merge consolidated.
    """
    repo = MagicMock()
    repo.get_id_by_github_login = AsyncMock(return_value=None)

    with (
        patch("app.services.identity_resolution.UserRepository", return_value=repo),
        patch(
            "app.services.identity_resolution.resolve_user_by_email",
            new=AsyncMock(return_value=_user(uuid.uuid4(), is_active=False)),
        ),
        patch(
            "app.services.identity_resolution.walk_to_active_user",
            new=AsyncMock(return_value=None),
        ),
    ):
        resolved = await resolve_canonical_user(
            _db_returning(None),
            uuid.uuid4(),
            email="stub@users.noreply.github.com",
        )

    assert resolved is None


@pytest.mark.asyncio
async def test_returns_none_when_both_miss() -> None:
    repo = MagicMock()
    repo.get_id_by_github_login = AsyncMock(return_value=None)

    with (
        patch("app.services.identity_resolution.UserRepository", return_value=repo),
        patch(
            "app.services.identity_resolution.resolve_user_by_email",
            new=AsyncMock(return_value=None),
        ),
    ):
        resolved = await resolve_canonical_user(
            _db_returning(None), uuid.uuid4(), github_login="ghost", email="ghost@x.io"
        )

    assert resolved is None


@pytest.mark.asyncio
async def test_no_identifiers_returns_none() -> None:
    resolved = await resolve_canonical_user(MagicMock(), uuid.uuid4())
    assert resolved is None
