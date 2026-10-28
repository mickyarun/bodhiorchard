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

"""Chat edits land in BUD history (#389) and the per-phase cap holds.

``persist_chat_update`` snapshots the pre-edit BUD under the section's
owning phase, attributed to the person who sent the chat message, so the
History tab can restore what the chat replaced. The per-phase ring
buffer keeps the newest 20 real edits and never counts reverts.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.bud import BUDStatus
from app.models.bud_version import MAX_VERSIONS_PER_PHASE, BUDEditSource, BUDVersion
from app.services.chat_persistence import persist_chat_update
from tests.integration.bud_lifecycle_reads import (
    load_bud,
)
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_member,
    as_user,
    new_org,
    stub_externals,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration


async def _history(factory: Factory, bud_id: uuid.UUID) -> list[BUDVersion]:
    """Every version row for the BUD, oldest version first."""
    async with factory() as db:
        rows = await db.scalars(
            select(BUDVersion)
            .where(BUDVersion.bud_id == bud_id)
            .order_by(BUDVersion.phase, BUDVersion.version_no)
        )
        return list(rows)


async def _chat(factory: Factory, bud_id: uuid.UUID, org: uuid.UUID, **kw: Any) -> None:
    """Run the chat write against the test database."""
    with stub_externals(), patch("app.services.chat_persistence.AsyncSessionLocal", factory):
        await persist_chat_update(str(bud_id), str(org), **kw)


async def test_chat_edit_is_snapshotted_and_revertible(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A chat rewrite of the requirements can be undone from History."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, requirements_md="hand written")

    await _chat(
        pg_session_factory,
        bud_id,
        org,
        section="requirements_md",
        content="chat rewrite",
        user_id=str(pm),
    )

    [row] = await _history(pg_session_factory, bud_id)
    assert (row.phase, row.source, row.reason) == (BUDStatus.BUD, BUDEditSource.AGENT, "chat edit")
    assert row.edited_by == pm
    assert row.snapshot["requirements_md"] == "hand written"
    assert (await load_bud(pg_session_factory, bud_id)).requirements_md == "chat rewrite"

    with stub_externals():
        res = await client.post(
            f"/api/v1/buds/{bud_id}/revert/bud/{row.version_no}", headers=as_user(pm, org)
        )

    assert res.status_code == 200
    assert (await load_bud(pg_session_factory, bud_id)).requirements_md == "hand written"


async def test_unchanged_chat_content_records_nothing(pg_session_factory: Factory) -> None:
    """Writing back the same text is not an edit."""
    org = await new_org(pg_session_factory)
    bud_id = await add_bud(pg_session_factory, org, requirements_md="same")

    await _chat(pg_session_factory, bud_id, org, section="requirements_md", content="same")

    assert await _history(pg_session_factory, bud_id) == []


async def test_chat_edit_files_under_the_owning_phase_not_the_live_status(
    pg_session_factory: Factory,
) -> None:
    """A tech-spec chat reply landing after the BUD advanced is filed under tech_arch."""
    org = await new_org(pg_session_factory)
    bud_id = await add_bud(
        pg_session_factory, org, status=BUDStatus.DESIGN, tech_spec_md="# Spec\nv1"
    )

    await _chat(pg_session_factory, bud_id, org, section="tech_spec_md", content="# Spec\nv2")

    [row] = await _history(pg_session_factory, bud_id)
    assert row.phase is BUDStatus.TECH_ARCH
    assert row.edited_by is None
    assert row.snapshot["tech_spec_md"] == "# Spec\nv1"


async def test_chat_edit_on_a_missing_bud_is_a_no_op(pg_session_factory: Factory) -> None:
    """A BUD deleted (or from another org) while the reply generated is skipped."""
    org = await new_org(pg_session_factory)
    other_org = await new_org(pg_session_factory)
    bud_id = await add_bud(pg_session_factory, other_org, requirements_md="theirs")

    await _chat(pg_session_factory, bud_id, org, section="requirements_md", content="mine")

    assert (await load_bud(pg_session_factory, bud_id)).requirements_md == "theirs"
    assert await _history(pg_session_factory, bud_id) == []


async def test_cap_keeps_newest_edits_and_ignores_reverts(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Past the cap the oldest edits go; a revert row neither counts nor evicts."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, title="t0")
    headers, url = as_user(pm, org), f"/api/v1/buds/{bud_id}"
    edits = MAX_VERSIONS_PER_PHASE + 2

    with stub_externals():
        for i in range(1, edits + 1):
            res = await client.patch(url, json={"title": f"t{i}"}, headers=headers)
            assert res.status_code == 200
        reverted = await client.post(f"{url}/revert/bud/{edits}", headers=headers)

    assert reverted.status_code == 200
    rows = await _history(pg_session_factory, bud_id)
    real = [r for r in rows if r.source is BUDEditSource.UI]
    reverts = [r for r in rows if r.source is BUDEditSource.REVERT]
    assert len(real) == MAX_VERSIONS_PER_PHASE
    assert [r.version_no for r in real] == list(range(3, edits + 1))
    assert [r.version_no for r in reverts] == [edits + 1]
    # The newest version (``edits``) holds the title as it was before the last edit.
    assert (await load_bud(pg_session_factory, bud_id)).title == f"t{edits - 1}"
