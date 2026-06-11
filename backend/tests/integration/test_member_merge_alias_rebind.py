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

"""Alias rebind + unlink behaviour around member merges.

Regression coverage for the "stranded alias" defect: a botched merge
could leave an email aliased to a now-deactivated user, and the
original merge handler's ``add_email_alias`` short-circuited on the
``(org_id, email)`` conflict — so subsequent merges could not reclaim
the email. Every later scan continued to route that email's commits
into the dead user.

Three properties verified end-to-end against a real Postgres:

1. ``rebind_aliases_to_target`` overwrites a pre-existing conflicting
   alias row (rather than silently keeping the stale one).
2. ``delete_alias`` is user-scoped — removing on a mismatched
   ``user_id`` is a no-op so concurrent admins on stale pages can't
   clobber each other.
3. The full merge flow, exercised at the repository layer, leaves the
   alias attached to the *new* target — even when an earlier bad merge
   left it stranded on a now-deactivated user.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization
from app.models.user import OrgToUser, User, UserEmailAlias
from app.repositories.user import UserRepository

pytestmark = pytest.mark.integration


async def _seed_org_and_user(
    factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
    is_active: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a fresh org + one user + membership; return ``(org_id, user_id)``."""
    async with factory() as db:
        org = Organization(
            name=f"Merge Test Org {uuid.uuid4()}",
            slug=f"merge-{uuid.uuid4().hex[:8]}",
        )
        db.add(org)
        await db.flush()

        user = User(
            email=email,
            name=email.split("@", 1)[0],
            password_hash="x",
            is_active=is_active,
        )
        db.add(user)
        await db.flush()
        db.add(OrgToUser(user_id=user.id, org_id=org.id))
        await db.commit()
        return org.id, user.id


async def _add_user(
    factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    email: str,
    *,
    is_active: bool = True,
) -> uuid.UUID:
    """Add one more user + membership to an existing org."""
    async with factory() as db:
        user = User(
            email=email, name=email.split("@", 1)[0], password_hash="x", is_active=is_active
        )
        db.add(user)
        await db.flush()
        db.add(OrgToUser(user_id=user.id, org_id=org_id))
        await db.commit()
        return user.id


def _unique(prefix: str) -> str:
    """Email with a per-call uuid suffix so tests sharing the DB don't collide."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


@pytest.mark.asyncio
async def test_rebind_overwrites_pre_existing_alias(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reproduces the stranded-alias defect at the primitive layer.

    Pre-seed an alias pointing at user B. Call
    ``rebind_aliases_to_target`` to claim the same email for user C.
    The DB must end with exactly one row, pointing at C — proving that
    the stale row was cleared rather than silently kept.
    """
    org_id, user_b = await _seed_org_and_user(pg_session_factory, email=_unique("b"))
    user_c = await _add_user(pg_session_factory, org_id, _unique("c"))
    contested = _unique("contested")

    async with pg_session_factory() as db:
        repo = UserRepository(db)
        # Earlier botched merge — alias attached to the wrong user.
        await repo.add_email_alias(org_id, user_b, contested)
        await db.commit()

    async with pg_session_factory() as db:
        repo = UserRepository(db)
        n = await repo.rebind_aliases_to_target(org_id, user_c, {contested})
        await db.commit()
        assert n == 1

    async with pg_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(UserEmailAlias).where(
                        UserEmailAlias.org_id == org_id,
                        UserEmailAlias.email == contested,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].user_id == user_c


@pytest.mark.asyncio
async def test_delete_alias_is_user_scoped(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``delete_alias`` only removes the row when ``user_id`` matches.

    Admin A on a stale page calls unlink on an alias that admin B has
    already reassigned to another member. The mismatched call must be a
    no-op (return False) so the row admin B intentionally created is
    not deleted.
    """
    org_id, user_b = await _seed_org_and_user(pg_session_factory, email=_unique("b"))
    user_c = await _add_user(pg_session_factory, org_id, _unique("c"))
    alias_email = _unique("alias")

    async with pg_session_factory() as db:
        repo = UserRepository(db)
        await repo.add_email_alias(org_id, user_c, alias_email)
        await db.commit()

    # Seed an identical alias in a *different* org. Cross-org isolation
    # must hold — a delete in org X cannot touch org Y's rows.
    other_org_id, other_user = await _seed_org_and_user(
        pg_session_factory, email=_unique("other-org-user")
    )
    async with pg_session_factory() as db:
        repo = UserRepository(db)
        await repo.add_email_alias(other_org_id, other_user, alias_email)
        await db.commit()

    async with pg_session_factory() as db:
        repo = UserRepository(db)
        # Wrong user_id — should be a no-op.
        removed = await repo.delete_alias(org_id, user_b, alias_email)
        assert removed is False
        # Right user_id — should remove.
        removed = await repo.delete_alias(org_id, user_c, alias_email)
        assert removed is True
        # Idempotent — second call returns False, no exception.
        removed = await repo.delete_alias(org_id, user_c, alias_email)
        assert removed is False

    async with pg_session_factory() as db:
        # Cross-org row survives untouched.
        rows = (
            (
                await db.execute(
                    select(UserEmailAlias).where(
                        UserEmailAlias.org_id == other_org_id,
                        UserEmailAlias.email == alias_email,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].user_id == other_user


@pytest.mark.asyncio
async def test_merge_carries_source_aliases_even_when_conflicting(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Full stranded-alias scenario at the rebind layer.

    Setup:

        1. Admin earlier merged some other user into S, so S already
           owns a stale alias ``carry_over``.
        2. Admin now merges S → target C. S's primary email AND every
           alias S currently owns must follow S onto C — even though
           one of those emails (``carry_over``) already has a row in
           ``user_email_aliases``.

    Pre-fix, ``add_email_alias`` short-circuited on the conflict and
    left the alias stranded on S. Post-fix, the rebind primitive
    deletes the stale row and re-points it at C, so the merge is
    actually atomic.
    """
    org_id, user_c = await _seed_org_and_user(pg_session_factory, email=_unique("target"))
    user_s = await _add_user(pg_session_factory, org_id, _unique("source"))
    carry_over = _unique("carry-over")
    source_email = _unique("source-primary")

    async with pg_session_factory() as db:
        repo = UserRepository(db)
        await repo.add_email_alias(org_id, user_s, carry_over)
        await db.commit()

    # Simulate the merge alias-rebind step: source S → target C.
    async with pg_session_factory() as db:
        repo = UserRepository(db)
        source_aliases = await repo.list_aliases(user_s)
        emails = {source_email} | {a.email for a in source_aliases}
        n = await repo.rebind_aliases_to_target(org_id, user_c, emails)
        await db.commit()
        assert n == 2

    async with pg_session_factory() as db:
        # Both emails now belong to C — no row left attached to S.
        rows = (
            (
                await db.execute(
                    select(UserEmailAlias).where(
                        UserEmailAlias.org_id == org_id,
                        UserEmailAlias.email.in_({source_email, carry_over}),
                    )
                )
            )
            .scalars()
            .all()
        )
        owners = {row.email: row.user_id for row in rows}
        assert owners == {source_email: user_c, carry_over: user_c}
