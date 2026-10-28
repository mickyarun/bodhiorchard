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

"""Sign-in, token refresh and the forced password change, end to end over HTTP."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update

from app.config import settings
from app.models.user import OrgToUser, User
from tests.integration.auth_tenancy_support import PASSWORD, add_user, new_tenant
from tests.integration.leave_support import Factory

pytestmark = pytest.mark.integration
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/auth/me"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient, email: str, slug: str, password: str = PASSWORD) -> dict:
    response = await client.post(
        LOGIN, json={"email": email, "password": password, "org_slug": slug}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_login_gives_tokens_that_work_and_refresh(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    tokens = await _login(client, t.owner_email, t.slug)
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == settings.auth.access_token_expire_minutes * 60
    assert tokens["must_change_password"] is False

    me = await client.get(ME, headers=_bearer(tokens["access_token"]))
    assert me.status_code == 200, me.text
    body = me.json()
    assert (body["id"], body["org_id"], body["role"]) == (str(t.owner), str(t.org), "org_owner")
    assert "team:assign_roles" in body["permissions"]

    renewed = await client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert renewed.status_code == 200, renewed.text
    again = await client.get(ME, headers=_bearer(renewed.json()["access_token"]))
    assert again.json()["org_id"] == str(t.org)


async def test_every_wrong_sign_in_gets_the_same_answer(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Nothing in the response says whether the email, org or password was wrong."""
    a = await new_tenant(pg_session_factory)
    b = await new_tenant(pg_session_factory)
    async with pg_session_factory() as db:
        await db.execute(update(User).where(User.id == a.dev).values(is_active=False))
        await db.commit()
    attempts = {
        "wrong password": (a.owner_email, a.slug, PASSWORD + "x"),
        "unknown org": (a.owner_email, f"nope-{uuid.uuid4().hex[:6]}", PASSWORD),
        "another org's slug": (a.owner_email, b.slug, PASSWORD),
        "unknown email": (f"ghost-{uuid.uuid4().hex[:6]}@tenancy.dev", a.slug, PASSWORD),
        "deactivated": (a.dev_email, a.slug, PASSWORD),
    }
    for label, (email, slug, password) in attempts.items():
        response = await client.post(
            LOGIN, json={"email": email, "password": password, "org_slug": slug}
        )
        assert response.status_code == 401, label
        assert response.json() == {"detail": "Invalid credentials"}, label


async def test_a_forced_password_change_blocks_everything_until_done(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    _hire, email = await add_user(
        pg_session_factory, t.org, "developer", must_change_password=True
    )
    tokens = await _login(client, email, t.slug)
    assert tokens["must_change_password"] is True
    headers = _bearer(tokens["access_token"])
    for path in (ME, "/api/v1/members/directory", "/api/v1/features"):
        blocked = await client.get(path, headers=headers)
        assert (blocked.status_code, blocked.json()) == (
            403,
            {"detail": "Password change required"},
        ), path

    change = "/api/v1/auth/change-password"
    short = await client.post(change, json={"new_password": "7-chars"}, headers=headers)
    assert short.status_code == 422
    chosen = "pässwörd-ünï-🔑-long"
    done = await client.post(change, json={"new_password": chosen}, headers=headers)
    assert done.status_code == 200, done.text

    assert (await client.get(ME, headers=headers)).status_code == 200
    old = await client.post(LOGIN, json={"email": email, "password": PASSWORD, "org_slug": t.slug})
    assert old.status_code == 401
    fresh = await _login(client, email, t.slug, chosen)
    assert fresh["must_change_password"] is False


async def test_refresh_is_refused_for_the_wrong_token_or_a_lost_member(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    owner = await _login(client, t.owner_email, t.slug)
    dev = await _login(client, t.dev_email, t.slug)

    as_refresh = await client.post(REFRESH, json={"refresh_token": owner["access_token"]})
    assert as_refresh.status_code == 401
    garbage = await client.post(REFRESH, json={"refresh_token": "not.a.token"})
    assert garbage.status_code == 401
    as_access = await client.get(ME, headers=_bearer(owner["refresh_token"]))
    assert as_access.status_code == 401

    async with pg_session_factory() as db:
        await db.execute(
            delete(OrgToUser).where(OrgToUser.user_id == t.dev, OrgToUser.org_id == t.org)
        )
        await db.execute(update(User).where(User.id == t.owner).values(is_active=False))
        await db.commit()
    removed = await client.post(REFRESH, json={"refresh_token": dev["refresh_token"]})
    assert removed.status_code == 401
    assert removed.json() == {"detail": "User is no longer a member of this organization"}
    deactivated = await client.post(REFRESH, json={"refresh_token": owner["refresh_token"]})
    assert deactivated.status_code == 401
