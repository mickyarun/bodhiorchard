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

"""What a scan does with an author no email or alias points at yet.

A GitHub noreply address joins the member with that login, a machine's
default identity waits for an admin, and an org that turned auto-creation
off gets no new members from either a scan or a skill re-run.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.skill_rerun import rerun_skill_profiles
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import seed_member, seed_org, seed_repo
from tests.integration.scan_e2e.member_support import (
    aliases_of,
    commit_as,
    holds_profiles,
    member_by_email,
    org_member_emails,
    personal_address,
    scan,
    set_github_login,
    unmatched_authors,
)
from tests.integration.scan_e2e.scan_support import SYNTHESIS_MARKER, Factory, synthesis_writing

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_AUTO_CREATE_OFF = {"scan": {"auto_create_members": False}}


@pytest.fixture(autouse=True)
def _private_data_dir(data_dir: Path) -> Path:
    """Keep scan clones and worktrees under the test's tmp dir."""
    return data_dir


async def test_a_noreply_author_joins_the_member_with_that_github_login(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
) -> None:
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))
    org = await seed_org(app_sessions)
    bob = await seed_member(app_sessions, org.org_id, "bob")
    login = f"Bob-{uuid.uuid4().hex[:6]}"
    await set_github_login(app_sessions, bob, login)
    noreply = f"{uuid.uuid4().int % 10**8}+{login.lower()}@users.noreply.github.com"
    commit_as(shop_repo, noreply, {"shop/bob.py": "BOB = 1\n"})

    await scan(client, app_sessions, org, shop_repo)

    assert await member_by_email(app_sessions, org.org_id, noreply) is None
    assert noreply in await aliases_of(app_sessions, bob)
    assert await holds_profiles(app_sessions, org.org_id, bob)


async def test_a_machine_default_identity_waits_for_an_admin(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
) -> None:
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))
    org = await seed_org(app_sessions)
    laptop = f"dev-{uuid.uuid4().hex[:8]}@Some-MacBook-Pro.local"
    commit_as(shop_repo, laptop, {"shop/laptop.py": "OLD = 1\n"})

    result = await scan(client, app_sessions, org, shop_repo)

    assert await member_by_email(app_sessions, org.org_id, laptop) is None
    assert laptop in await unmatched_authors(app_sessions, org.org_id, result.scan_id)
    assert await member_by_email(app_sessions, org.org_id, shop_repo.author_email) is not None


async def test_a_scan_creates_no_members_when_the_org_turned_it_off(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    shop_repo: LocalGitRepo,
) -> None:
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))
    org = await seed_org(app_sessions, config=_AUTO_CREATE_OFF)
    before = await org_member_emails(app_sessions, org.org_id)

    result = await scan(client, app_sessions, org, shop_repo)

    assert await org_member_emails(app_sessions, org.org_id) == before
    assert shop_repo.author_email in await unmatched_authors(
        app_sessions, org.org_id, result.scan_id
    )


async def test_a_skill_rerun_creates_no_members_when_the_org_turned_it_off(
    app_sessions: Factory, shop_repo: LocalGitRepo
) -> None:
    org = await seed_org(app_sessions, config=_AUTO_CREATE_OFF)
    await seed_repo(app_sessions, org.org_id, shop_repo)
    commit_as(shop_repo, personal_address(), {"shop/side.py": "OLD = 1\n"})
    before = await org_member_emails(app_sessions, org.org_id)

    async with app_sessions() as db:
        result = await rerun_skill_profiles(db, org.org_id, wipe=False)
        await db.commit()

    assert await org_member_emails(app_sessions, org.org_id) == before
    assert result.unmatched_emails == 2
