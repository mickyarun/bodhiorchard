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

"""Tests for ``resolve_confirmed_repos`` — the shared repo-path resolver.

Backs the code-review repo-selection endpoint and the automatic PR-merge
transition. Only *active* tracked repos with a clone path resolve; the
caller treats an empty result as "nothing reviewable".
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.services.bud_repo_paths import resolve_confirmed_repos


async def _org(db: AsyncSession) -> uuid.UUID:
    org = Organization(name=f"CR {uuid.uuid4()}", slug=f"cr-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    return org.id


async def test_resolves_only_active_repos_in_the_selection(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as db:
        org_id = await _org(db)
        active = TrackedRepository(
            org_id=org_id, name="api", path="/data/repos/api", status=RepoStatus.ACTIVE
        )
        ignored = TrackedRepository(
            org_id=org_id, name="web", path="/data/repos/web", status=RepoStatus.IGNORED
        )
        db.add_all([active, ignored])
        await db.flush()

        # Select both, but only the active one resolves.
        result = await resolve_confirmed_repos(
            db, org_id, {str(active.id), str(ignored.id)}
        )
        assert result == [{"repo_path": "/data/repos/api", "repo_name": "api"}]


async def test_ids_outside_the_selection_are_excluded(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as db:
        org_id = await _org(db)
        a = TrackedRepository(
            org_id=org_id, name="a", path="/data/repos/a", status=RepoStatus.ACTIVE
        )
        b = TrackedRepository(
            org_id=org_id, name="b", path="/data/repos/b", status=RepoStatus.ACTIVE
        )
        db.add_all([a, b])
        await db.flush()

        result = await resolve_confirmed_repos(db, org_id, {str(a.id)})
        assert result == [{"repo_path": "/data/repos/a", "repo_name": "a"}]


async def test_empty_selection_resolves_to_nothing(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as db:
        org_id = await _org(db)
        db.add(
            TrackedRepository(
                org_id=org_id, name="a", path="/data/repos/a", status=RepoStatus.ACTIVE
            )
        )
        await db.flush()

        assert await resolve_confirmed_repos(db, org_id, set()) == []
