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

"""Identity transfer on member merge: PR history and the GitHub login.

Regression coverage for the split-identity defect. Every engineer had two
rows — a work-email member holding the role and BUD assignments, and a
provisioned GitHub stub holding all the pull requests. Merging them moved
XP, skill profiles and email aliases but left behind:

1. ``pull_requests.author_user_id`` on the deactivated stub, so the
   surviving member still reported zero throughput; and
2. ``users.github_username`` on the stub, so ``get_id_by_github_login``
   kept routing new PRs back to a deactivated row — the merge silently
   undid itself on the next webhook.

These tests pin both halves, plus the active-preference ordering that
keeps the lookup deterministic while duplicates still exist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization
from app.models.pull_request import PRState, PullRequest
from app.models.user import OrgToUser, User
from app.repositories.pull_request import PullRequestRepository
from app.repositories.user import UserRepository
from app.services.identity_resolution import resolve_canonical_user

pytestmark = pytest.mark.integration


async def _seed_org(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    """Create a fresh org and return its id."""
    async with factory() as db:
        org = Organization(
            name=f"Identity Org {uuid.uuid4()}",
            slug=f"identity-{uuid.uuid4().hex[:8]}",
        )
        db.add(org)
        await db.commit()
        return org.id


async def _add_user(
    factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    email: str,
    *,
    github_username: str | None = None,
    is_active: bool = True,
) -> uuid.UUID:
    """Add a user + membership to ``org_id``; return the user id."""
    async with factory() as db:
        user = User(
            email=email,
            name=email.split("@", 1)[0],
            password_hash="x",
            is_active=is_active,
            github_username=github_username,
        )
        db.add(user)
        await db.flush()
        db.add(OrgToUser(user_id=user.id, org_id=org_id))
        await db.commit()
        return user.id


async def _add_pr(
    factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    author_user_id: uuid.UUID,
    number: int,
) -> uuid.UUID:
    """Add one merged PR authored by ``author_user_id``."""
    async with factory() as db:
        pr = PullRequest(
            org_id=org_id,
            github_pr_number=number,
            github_pr_id=number + 900_000,
            github_repo_full_name="acme/api",
            title=f"PR {number}",
            html_url=f"https://github.com/acme/api/pull/{number}",
            head_branch=f"feat/{number}",
            base_branch="main",
            state=PRState.MERGED,
            author_github_login="devlogin",
            author_user_id=author_user_id,
            merged_at=datetime.now(UTC),
        )
        db.add(pr)
        await db.commit()
        return pr.id


def _unique(prefix: str) -> str:
    """Email with a per-call uuid suffix so tests sharing the DB don't collide."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


@pytest.mark.asyncio
async def test_repoint_author_moves_prs_to_target(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Every PR on the stub lands on the surviving member."""
    org_id = await _seed_org(pg_session_factory)
    stub = await _add_user(pg_session_factory, org_id, _unique("stub"), github_username="devlogin")
    real = await _add_user(pg_session_factory, org_id, _unique("real"))

    for number in (1, 2, 3):
        await _add_pr(pg_session_factory, org_id, stub, number)

    async with pg_session_factory() as db:
        moved = await PullRequestRepository(db, org_id=org_id).repoint_author(stub, real)
        await db.commit()

    assert moved == 3

    async with pg_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(PullRequest.author_user_id).where(PullRequest.org_id == org_id)
                )
            )
            .scalars()
            .all()
        )
    assert set(rows) == {real}


@pytest.mark.asyncio
async def test_repoint_author_is_org_scoped(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A merge in one org must not touch another org's PR attribution."""
    org_a = await _seed_org(pg_session_factory)
    org_b = await _seed_org(pg_session_factory)
    stub = await _add_user(pg_session_factory, org_a, _unique("stub"))
    real = await _add_user(pg_session_factory, org_a, _unique("real"))
    await _add_user(pg_session_factory, org_b, _unique("other"))

    await _add_pr(pg_session_factory, org_a, stub, 10)
    foreign_pr = await _add_pr(pg_session_factory, org_b, stub, 11)

    async with pg_session_factory() as db:
        moved = await PullRequestRepository(db, org_id=org_a).repoint_author(stub, real)
        await db.commit()

    assert moved == 1

    async with pg_session_factory() as db:
        untouched = await db.get(PullRequest, foreign_pr)
        assert untouched is not None
        assert untouched.author_user_id == stub


@pytest.mark.asyncio
async def test_github_login_lookup_prefers_active_member(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A deactivated duplicate must never win the login lookup."""
    org_id = await _seed_org(pg_session_factory)
    await _add_user(
        pg_session_factory,
        org_id,
        _unique("dead"),
        github_username="devlogin",
        is_active=False,
    )
    alive = await _add_user(
        pg_session_factory, org_id, _unique("alive"), github_username="devlogin"
    )

    async with pg_session_factory() as db:
        resolved = await UserRepository(db).get_id_by_github_login(org_id, "devlogin")

    assert resolved == alive


@pytest.mark.asyncio
async def test_github_login_lookup_is_case_insensitive(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GitHub logins are case-insensitive; the lookup must match that."""
    org_id = await _seed_org(pg_session_factory)
    user_id = await _add_user(
        pg_session_factory, org_id, _unique("mixed"), github_username="Mixed-Case-Dev"
    )

    async with pg_session_factory() as db:
        repo = UserRepository(db)
        assert await repo.get_id_by_github_login(org_id, "mixed-case-dev") == user_id
        assert await repo.get_id_by_github_login(org_id, "MIXED-CASE-DEV") == user_id


@pytest.mark.asyncio
async def test_login_survives_when_target_already_has_one(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A target's own login must not silently destroy the source's.

    There is no alias table for GitHub logins, so clearing the source
    when the target already owns a different login would erase the only
    record of that identity — the next PR under it would provision a
    fresh stub and re-split the member the merge just consolidated.
    """
    org_id = await _seed_org(pg_session_factory)
    stub = await _add_user(pg_session_factory, org_id, _unique("stub"), github_username="oldlogin")
    target = await _add_user(
        pg_session_factory, org_id, _unique("real"), github_username="newlogin"
    )

    async with pg_session_factory() as db:
        src = await db.get(User, stub)
        tgt = await db.get(User, target)
        assert src is not None and tgt is not None
        # Mirror the handler's guarded transfer.
        if src.github_username and not tgt.github_username:
            tgt.github_username = src.github_username
            src.github_username = None
        src.is_active = False
        await db.commit()

    async with pg_session_factory() as db:
        src = await db.get(User, stub)
        tgt = await db.get(User, target)
        assert src is not None and tgt is not None
        assert tgt.github_username == "newlogin"
        assert src.github_username == "oldlogin"


@pytest.mark.asyncio
async def test_resolution_walks_from_deactivated_stub_to_target(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The noreply address must resolve past a merged-away stub.

    A stub keeps its primary email after the merge, and
    resolve_user_by_email matches primary addresses before aliases, so
    without the alias walk this lands on the deactivated stub.
    """
    org_id = await _seed_org(pg_session_factory)
    noreply = f"devlogin-{uuid.uuid4().hex[:6]}@users.noreply.github.com"
    stub = await _add_user(pg_session_factory, org_id, noreply)
    target = await _add_user(pg_session_factory, org_id, _unique("real"))

    async with pg_session_factory() as db:
        repo = UserRepository(db)
        await repo.rebind_aliases_to_target(org_id, target, {noreply})
        src = await db.get(User, stub)
        assert src is not None
        src.is_active = False
        await db.commit()

    async with pg_session_factory() as db:
        resolved = await resolve_canonical_user(db, org_id, email=noreply)

    assert resolved == target


@pytest.mark.asyncio
async def test_resolution_stops_on_alias_cycle(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A cycle between two deactivated rows must not loop forever."""
    org_id = await _seed_org(pg_session_factory)
    email_a, email_b = _unique("a"), _unique("b")
    user_a = await _add_user(pg_session_factory, org_id, email_a, is_active=False)
    user_b = await _add_user(pg_session_factory, org_id, email_b, is_active=False)

    async with pg_session_factory() as db:
        repo = UserRepository(db)
        await repo.add_email_alias(org_id, user_b, email_a)
        await repo.add_email_alias(org_id, user_a, email_b)
        await db.commit()

    async with pg_session_factory() as db:
        assert await resolve_canonical_user(db, org_id, email=email_a) is None
