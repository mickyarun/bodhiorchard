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

"""The release-driven auto-close (``_maybe_auto_close_bud``).

A prod / UAT BUD closes once every impacted repo has a ``merged_to_prod``
event, runs the closure hook once, and a repeat delivery is a no-op.
Partial releases and BUDs outside prod / UAT are left alone.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.bud import BUDStatus
from app.services.bud_timeline import record_event
from app.services.release_detection import _maybe_auto_close_bud
from tests.integration.bud_lifecycle_reads import load_bud, timeline, xp_events
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_commit,
    add_member,
    new_org,
    stub_externals,
)

pytestmark = pytest.mark.integration

REPOS = [str(uuid.uuid4()), str(uuid.uuid4())]


async def _released_bud(
    factory: Factory, status: BUDStatus, released: list[str]
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A BUD on two impacted repos, ``released`` of them merged to prod."""
    org = await new_org(factory)
    dev = await add_member(factory, org, "dev", role="developer")
    bud_id = await add_bud(
        factory,
        org,
        number=9,
        status=status,
        impacted_repos=[{"repo_id": r, "repo_name": f"repo{i}"} for i, r in enumerate(REPOS)],
    )
    await add_commit(factory, org, bud_id, dev)
    async with factory() as db:
        for repo_id in released:
            await record_event(db, org, bud_id, "merged_to_prod", detail={"repo_id": repo_id})
        await db.commit()
    return org, bud_id, dev


async def _run(factory: Factory, org: uuid.UUID, bud_id: uuid.UUID) -> None:
    """One webhook delivery's worth of auto-close, committed."""
    async with factory() as db:
        with stub_externals():
            await _maybe_auto_close_bud(db, org, bud_id)
        await db.commit()


@pytest.mark.parametrize("status", [BUDStatus.PROD, BUDStatus.UAT])
async def test_full_release_closes_once_and_pays_once(
    pg_session_factory: Factory, status: BUDStatus
) -> None:
    """Every repo released: closed, one auto status change, contributor paid once."""
    org, bud_id, dev = await _released_bud(pg_session_factory, status, REPOS)

    await _run(pg_session_factory, org, bud_id)
    await _run(pg_session_factory, org, bud_id)

    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.CLOSED
    changes = await timeline(pg_session_factory, bud_id, "status_change")
    assert [(c["to"], c["auto"]) for c in changes] == [("closed", True)]
    assert await xp_events(pg_session_factory, org) == {f"bud_contrib:9:{dev}": 25}


async def test_partial_release_keeps_the_bud_open(pg_session_factory: Factory) -> None:
    """One of two repos released: nothing changes."""
    org, bud_id, _dev = await _released_bud(pg_session_factory, BUDStatus.PROD, REPOS[:1])

    await _run(pg_session_factory, org, bud_id)

    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.PROD
    assert await xp_events(pg_session_factory, org) == {}


@pytest.mark.parametrize("status", [BUDStatus.TESTING, BUDStatus.DISCARDED])
async def test_only_prod_or_uat_buds_auto_close(
    pg_session_factory: Factory, status: BUDStatus
) -> None:
    """A testing or discarded BUD is never closed by a release event."""
    org, bud_id, _dev = await _released_bud(pg_session_factory, status, REPOS)

    await _run(pg_session_factory, org, bud_id)

    assert (await load_bud(pg_session_factory, bud_id)).status is status
    assert await timeline(pg_session_factory, bud_id, "status_change") == []


async def test_bud_without_impacted_repos_never_auto_closes(pg_session_factory: Factory) -> None:
    """No impacted repos means nothing to wait for and nothing to close on."""
    org = await new_org(pg_session_factory)
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.PROD)

    await _run(pg_session_factory, org, bud_id)

    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.PROD
