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

"""A rescan honours the identity decisions an admin already made.

Skill extraction auto-creates a member for every git author it can't
place. An address that is already an alias, or that an admin merged away
or deactivated, must land on the person the admin chose, and a genuinely
new author must still become a member.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import auth_headers, seed_member, seed_org
from tests.integration.scan_e2e.member_support import (
    add_alias,
    commit_as,
    holds_profiles,
    member_by_email,
    org_member_emails,
    personal_address,
    scan,
)
from tests.integration.scan_e2e.scan_support import SYNTHESIS_MARKER, Factory, synthesis_writing

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(autouse=True)
def _private_data_dir(data_dir: Path) -> Path:
    """Keep scan clones and worktrees under the test's tmp dir."""
    return data_dir


async def test_an_alias_author_lands_on_the_member_who_owns_the_alias(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
) -> None:
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))
    org = await seed_org(app_sessions)
    alice = await seed_member(app_sessions, org.org_id, "alice")
    noreply = f"{uuid.uuid4().int % 10**8}+alice@users.noreply.github.com"
    await add_alias(app_sessions, org.org_id, alice, noreply)
    commit_as(shop_repo, noreply.upper(), {"shop/alias_note.py": "NOTE = 1\n"})
    before = await org_member_emails(app_sessions, org.org_id)

    await scan(client, app_sessions, org, shop_repo)

    after = await org_member_emails(app_sessions, org.org_id)
    assert after == before | {shop_repo.author_email}
    assert await holds_profiles(app_sessions, org.org_id, alice)


async def test_a_merged_address_is_not_recreated_on_a_rescan(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
) -> None:
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))
    org = await seed_org(app_sessions)
    alice = await seed_member(app_sessions, org.org_id, "alice")
    personal = personal_address()
    commit_as(shop_repo, personal, {"shop/side.py": "OLD = 1\n"})
    first = await scan(client, app_sessions, org, shop_repo)
    stub = await member_by_email(app_sessions, org.org_id, personal)
    assert stub is not None and stub.is_active, "the first scan should auto-create the author"

    headers = auth_headers(org.owner_id, org.org_id)
    merged = await client.post(
        f"/api/v1/members/{alice}/merge", json={"sourceId": str(stub.id)}, headers=headers
    )
    assert merged.status_code == 200, merged.text
    await scan(client, app_sessions, org, shop_repo, repo_id=first.repo_id)

    again = await member_by_email(app_sessions, org.org_id, personal)
    assert again is not None and again.id == stub.id and not again.is_active
    assert await holds_profiles(app_sessions, org.org_id, alice)
    assert not await holds_profiles(app_sessions, org.org_id, stub.id)


async def test_a_deactivated_author_stays_deactivated_on_a_rescan(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
) -> None:
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))
    org = await seed_org(app_sessions)
    personal = personal_address()
    commit_as(shop_repo, personal, {"shop/side.py": "OLD = 1\n"})
    first = await scan(client, app_sessions, org, shop_repo)
    stub = await member_by_email(app_sessions, org.org_id, personal)
    assert stub is not None

    headers = auth_headers(org.owner_id, org.org_id)
    removed = await client.patch(f"/api/v1/members/{stub.id}/status", headers=headers)
    assert removed.status_code == 200, removed.text
    before = await org_member_emails(app_sessions, org.org_id)
    await scan(client, app_sessions, org, shop_repo, repo_id=first.repo_id)

    again = await member_by_email(app_sessions, org.org_id, personal)
    assert again is not None and again.id == stub.id and not again.is_active
    assert await org_member_emails(app_sessions, org.org_id) == before


async def test_a_genuinely_new_author_is_still_created(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    git_repo_factory: Callable[..., LocalGitRepo],
) -> None:
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))
    repo = git_repo_factory("shop-api", author_email=f"new-{uuid.uuid4().hex[:8]}@example.test")
    org = await seed_org(app_sessions)
    newcomer = personal_address()
    commit_as(repo, newcomer, {"shop/new.py": "NEW = 1\n"})

    await scan(client, app_sessions, org, repo)

    created = await member_by_email(app_sessions, org.org_id, newcomer)
    assert created is not None and created.is_active
    assert await holds_profiles(app_sessions, org.org_id, created.id)
