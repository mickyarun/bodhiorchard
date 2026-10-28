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

"""Stage one of the setup wizard against Postgres.

``setup_init_org`` is called directly: its HTTP route refuses once any
org exists, and the session's shared database always has some. That
gate has its own tests (``tests/api/v1/test_setup_complete_gate.py``).
Process env and the clone root are kept out of reach: the env push is
recorded, and clones live under ``tmp_path``.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import settings as app_settings
from app.core.security import verify_password, verify_token
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import OrgToUser, User
from app.schemas.setup import InitOrgRequest
from app.services import setup_init
from tests.integration.settings_support import Factory, assert_ciphertext_of

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def env_pushes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[Organization]:
    """Keep clones in ``tmp_path`` and record, not apply, the env push."""
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
    pushed: list[Organization] = []
    monkeypatch.setattr(setup_init, "apply_claude_auth_to_env", pushed.append)
    return pushed


def _request(slug: str, **claude: object) -> InitOrgRequest:
    return InitOrgRequest.model_validate(
        {
            "organization": {"name": "Acme", "slug": slug},
            "admin": {
                "email": f"owner-{slug}@acme.dev",
                "name": "Owner",
                "password": "correct-horse",
            },
            "claude": claude or {"authMode": "host"},
        }
    )


def _slug() -> str:
    return f"init-{uuid.uuid4().hex[:10]}"


async def _count(factory: Factory, slug: str) -> tuple[int, int]:
    """(orgs with this slug, users with this slug's admin email)."""
    async with factory() as db:
        orgs = await db.scalar(select(func.count()).where(Organization.slug == slug))
        users = await db.scalar(select(func.count()).where(User.email == f"owner-{slug}@acme.dev"))
        return int(orgs or 0), int(users or 0)


async def test_provisions_an_owner_with_secrets_at_rest_only_as_hashes_or_ciphertext(
    pg_session_factory: Factory, env_pushes: list[Organization]
) -> None:
    slug = _slug()
    async with pg_session_factory() as db:
        result = await setup_init.setup_init_org(
            _request(slug, authMode="api_key", apiKey="  sk-ant-secret-123  "), db
        )

    async with pg_session_factory() as db:
        org = await db.get(Organization, result.org.id)
        assert org is not None
        assert org.claude_auth_mode == "api_key"
        assert_ciphertext_of(org.claude_api_key_encrypted, "sk-ant-secret-123")
        assert verify_password(result.mcp_token, org.mcp_token_hash or "")
        assert result.mcp_token not in (org.mcp_token_hash or "")
        role_name = await db.scalar(
            select(Role.name)
            .join(OrgToUser, OrgToUser.role_id == Role.id)
            .where(OrgToUser.org_id == org.id, OrgToUser.user_id == result.user.id)
        )
        assert role_name == "org_owner"

    claims = verify_token(result.access_token)
    assert claims is not None
    assert (claims["sub"], claims["org_id"]) == (str(result.user.id), str(result.org.id))
    assert [o.id for o in env_pushes] == [result.org.id]


async def test_subscription_token_is_encrypted_and_host_stores_nothing(
    pg_session_factory: Factory,
) -> None:
    sub_slug, host_slug = _slug(), _slug()
    async with pg_session_factory() as db:
        sub = await setup_init.setup_init_org(
            _request(sub_slug, authMode="subscription", oauthToken="oat-xyz"), db
        )
    async with pg_session_factory() as db:
        host = await setup_init.setup_init_org(_request(host_slug), db)

    async with pg_session_factory() as db:
        sub_org = await db.get(Organization, sub.org.id)
        host_org = await db.get(Organization, host.org.id)
        assert sub_org is not None and host_org is not None
        assert_ciphertext_of(sub_org.claude_api_key_encrypted, "oat-xyz")
        assert host_org.claude_api_key_encrypted is None


async def test_a_second_call_with_the_same_slug_is_a_409_and_adds_nothing(
    pg_session_factory: Factory,
) -> None:
    slug = _slug()
    async with pg_session_factory() as db:
        await setup_init.setup_init_org(_request(slug), db)

    async with pg_session_factory() as db:
        with pytest.raises(HTTPException) as caught:
            await setup_init.setup_init_org(_request(slug), db)
        await db.rollback()

    assert caught.value.status_code == 409
    assert await _count(pg_session_factory, slug) == (1, 1)


@pytest.mark.parametrize(
    "claude",
    [
        {"authMode": "api_key", "apiKey": "   "},
        {"authMode": "subscription"},
        {"provider": "skynet"},
        {"provider": "claude", "authMode": "pigeon"},
    ],
)
async def test_a_bad_ai_choice_is_a_400_and_creates_nothing(
    pg_session_factory: Factory, claude: dict[str, object]
) -> None:
    slug = _slug()
    async with pg_session_factory() as db:
        with pytest.raises(HTTPException) as caught:
            await setup_init.setup_init_org(_request(slug, **claude), db)
        await db.rollback()

    assert caught.value.status_code == 400
    assert await _count(pg_session_factory, slug) == (0, 0)


async def test_leftover_clones_for_the_slug_are_purged_and_others_kept(
    pg_session_factory: Factory,
) -> None:
    slug = _slug()
    repos = app_settings.storage.repos_dir
    (repos / slug / "stale" / ".git").mkdir(parents=True)
    (repos / "someone-else" / "live" / ".git").mkdir(parents=True)

    async with pg_session_factory() as db:
        await setup_init.setup_init_org(_request(slug), db)

    assert not (repos / slug).exists()
    assert (repos / "someone-else" / "live" / ".git").is_dir()
