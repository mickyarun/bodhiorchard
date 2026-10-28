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

"""A bearer token only works if it is genuine, current and names a live membership.

Each forged or stale token is sent to a real route backed by Postgres; the
route-walk unit test separately proves every protected route answers 401
to a bad token before touching the database.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy import delete, update

from app.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.models.user import OrgToUser, User
from tests.integration.auth_tenancy_support import new_tenant
from tests.integration.leave_support import Factory, as_user

pytestmark = pytest.mark.integration
ME = "/api/v1/auth/me"
FAR_FUTURE = 4_102_444_800


def _b64(part: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()


def _signed(claims: dict[str, Any]) -> str:
    return str(jwt.encode(claims, settings.auth.secret_key, algorithm=settings.auth.algorithm))


def _forgeries(user: uuid.UUID, org: uuid.UUID, owner: uuid.UUID) -> dict[str, str]:
    """Tokens a caller might try in place of a real one, keyed by what's wrong."""
    claims = {"sub": str(user), "org_id": str(org), "type": "access", "exp": FAR_FUTURE}
    genuine = create_access_token({"sub": str(user), "org_id": str(org)})
    header, _payload, signature = genuine.split(".")
    as_owner = _b64({**claims, "sub": str(owner)})
    return {
        "payload swapped under a valid signature": f"{header}.{as_owner}.{signature}",
        "signed with another key": jwt.encode(claims, "guessed-secret", algorithm="HS256"),
        "alg none": f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}.",
        "expired": create_access_token(
            {"sub": str(user), "org_id": str(org)}, expires_delta=timedelta(seconds=-5)
        ),
        "refresh token": create_refresh_token({"sub": str(user), "org_id": str(org)}),
        "no sub": _signed({k: v for k, v in claims.items() if k != "sub"}),
        "no org": _signed({k: v for k, v in claims.items() if k != "org_id"}),
        "sub not a uuid": _signed({**claims, "sub": "admin"}),
        "unknown user": _signed({**claims, "sub": str(uuid.uuid4())}),
        "not a jwt": "definitely-not-a-jwt",
    }


async def test_forged_and_stale_tokens_are_rejected(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    let_in = {}
    for label, token in _forgeries(t.dev, t.org, t.owner).items():
        response = await client.get(ME, headers={"Authorization": f"Bearer {token}"})
        if response.status_code != 401:
            let_in[label] = response.status_code
    assert let_in == {}


async def test_the_header_must_be_a_bearer_token(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    token = create_access_token({"sub": str(t.dev), "org_id": str(t.org)})
    assert (await client.get(ME)).status_code == 401
    basic = await client.get(ME, headers={"Authorization": f"Basic {token}"})
    assert basic.status_code == 401
    bare = await client.get(ME, headers={"Authorization": token})
    assert bare.status_code == 401
    # The scheme name is case-insensitive (RFC 7235).
    lower = await client.get(ME, headers={"Authorization": f"bearer {token}"})
    assert lower.status_code == 200


async def test_a_token_for_an_org_you_are_not_in_is_forbidden(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    a = await new_tenant(pg_session_factory)
    b = await new_tenant(pg_session_factory)
    # Genuinely signed, but a.dev has no membership in b's org.
    token = create_access_token({"sub": str(a.dev), "org_id": str(b.org)})
    response = await client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Not a member of this organization"}


async def test_losing_access_ends_a_live_session_at_once(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Deactivation or removal applies to the very next request, not at token expiry."""
    t = await new_tenant(pg_session_factory)
    dev = as_user(t.dev, t.org)
    owner = as_user(t.owner, t.org)
    assert (await client.get(ME, headers=dev)).status_code == 200
    assert (await client.get(ME, headers=owner)).status_code == 200
    async with pg_session_factory() as db:
        await db.execute(update(User).where(User.id == t.dev).values(is_active=False))
        await db.execute(
            delete(OrgToUser).where(OrgToUser.user_id == t.owner, OrgToUser.org_id == t.org)
        )
        await db.commit()
    assert (await client.get(ME, headers=dev)).status_code == 401
    assert (await client.get(ME, headers=owner)).status_code == 403


async def test_a_token_minted_before_the_type_claim_still_works(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    t = await new_tenant(pg_session_factory)
    legacy = _signed({"sub": str(t.dev), "org_id": str(t.org), "exp": FAR_FUTURE})
    response = await client.get(ME, headers={"Authorization": f"Bearer {legacy}"})
    assert response.status_code == 200
    assert response.json()["id"] == str(t.dev)
