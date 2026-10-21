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

"""HR generates (never set) or resets (already set) a password from the employee record."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.security import verify_password
from app.models.user import User
from tests.integration.leave_support import (
    Factory,
    as_user,
    give_custom_role,
    give_role,
    setup_org,
)

pytestmark = pytest.mark.integration


async def _chose_own(factory: Factory, user_id: uuid.UUID) -> None:
    """As if they signed in and chose their own password."""
    async with factory() as db:
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(must_change_password=False, password_set_at=datetime.now(UTC))
        )
        await db.commit()


async def test_generate_for_a_new_hire_then_reset_once_they_set_their_own(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr, hire), _ = await setup_org(pg_session_factory, "Hr", "Hire")
    await give_role(pg_session_factory, org, hr, "hr")
    headers = as_user(hr, org)
    # Made by an import, or invited: they've never chosen a password.

    login = await client.get(f"/api/v1/employees/{hire}/login", headers=headers)
    assert login.status_code == 200, login.text
    assert login.json()["action"] == "generate"

    made = await client.post(f"/api/v1/employees/{hire}/login/password", headers=headers)
    assert made.status_code == 200, made.text
    result = made.json()
    assert result["action"] == "generate" and result["login_url"].endswith("/login")
    async with pg_session_factory() as db:
        user = await db.get(User, hire)
        assert user is not None and user.must_change_password is True
        assert user.password_set_at is None
        assert verify_password(result["password"], user.password_hash)
    # Still theirs to choose, so it's still "generate".
    again = await client.get(f"/api/v1/employees/{hire}/login", headers=headers)
    assert again.json()["action"] == "generate"

    # They sign in and choose their own: HR's button now resets.
    await _chose_own(pg_session_factory, hire)
    login = await client.get(f"/api/v1/employees/{hire}/login", headers=headers)
    assert login.json()["action"] == "reset"
    reset = await client.post(f"/api/v1/employees/{hire}/login/password", headers=headers)
    assert reset.json()["action"] == "reset"
    async with pg_session_factory() as db:
        user = await db.get(User, hire)
        assert user is not None and user.must_change_password is True
        assert user.password_set_at is None


async def test_only_hr_and_never_on_their_own_record(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr, peer), _ = await setup_org(pg_session_factory, "Hr", "Peer")
    await give_role(pg_session_factory, org, hr, "hr")
    # HR can't reset their own password here (that's the change-password screen).
    own = await client.post(f"/api/v1/employees/{hr}/login/password", headers=as_user(hr, org))
    assert own.status_code == 403
    # Someone without employees:manage can't reset HR's (or anyone's).
    peer_try = await client.post(
        f"/api/v1/employees/{hr}/login/password", headers=as_user(peer, org)
    )
    assert peer_try.status_code == 403
    # The access flag the profile page uses says the same.
    record = await client.get(f"/api/v1/employees/{peer}", headers=as_user(hr, org))
    assert record.json()["access"]["reset_password"] is True
    mine = await client.get(f"/api/v1/employees/{hr}", headers=as_user(hr, org))
    assert mine.json()["access"]["reset_password"] is False


async def test_hr_cannot_take_over_anyone_with_more_access_or_elsewhere(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr, admin, owner), _ = await setup_org(pg_session_factory, "Hr", "Admin", "Owner")
    await give_role(pg_session_factory, org, hr, "hr")
    await give_role(pg_session_factory, org, admin, "admin")
    await give_role(pg_session_factory, org, owner, "org_owner")
    headers = as_user(hr, org)
    for target in (admin, owner):
        tried = await client.post(f"/api/v1/employees/{target}/login/password", headers=headers)
        assert tried.status_code == 403, (target, tried.text)
    # Someone in another org is simply not found here.
    _other, (stranger,), _ = await setup_org(pg_session_factory, "Stranger")
    away = await client.post(f"/api/v1/employees/{stranger}/login/password", headers=headers)
    assert away.status_code == 404


async def test_employee_admin_without_document_access_cannot(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Their documents and IDs are behind a sign-in, so taking it over needs that access too."""
    org, (clerk, peer), _ = await setup_org(pg_session_factory, "Clerk", "Peer")
    await give_custom_role(pg_session_factory, org, clerk, "employees:manage", "employees:view")
    headers = as_user(clerk, org)
    record = await client.get(f"/api/v1/employees/{peer}", headers=headers)
    assert record.json()["access"]["reset_password"] is False
    tried = await client.post(f"/api/v1/employees/{peer}/login/password", headers=headers)
    assert tried.status_code == 403
