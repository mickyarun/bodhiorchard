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

"""A stage agent's unusable output never replaces the section the BUD already has.

The result handlers run on real rows. An empty tech spec or unreadable test
cases raise before anything is written, which the BUD agent handler turns
into a failed task with the section untouched.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_agent_task import BUDAgentTask
from app.models.organization import Organization
from app.services import agent_result_handlers
from app.services.agent_result_handlers import (
    UnusableAgentOutputError,
    handle_tech_arch_result,
    handle_testing_result,
)

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
MANUAL = [{"id": "TC-001", "result": "passed", "evidence": ["shot.png"], "tester_name": "Ana"}]


async def _no_estimate(*args: object, **kwargs: object) -> None:
    """Stands in for the estimator, which would run an agent of its own."""


async def _bud(factory: Factory, **columns: object) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        org = Organization(name=f"Acme {uuid.uuid4().hex[:6]}", slug=f"a-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", **columns)
        db.add(bud)
        await db.commit()
        return org.id, bud.id


async def _reread(factory: Factory, bud_id: uuid.UUID) -> BUDDocument:
    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        return bud


@pytest.mark.parametrize("output", ["", "★ Insight ─────\nnothing\n─────"])
async def test_empty_tech_spec_keeps_the_current_one(
    pg_session_factory: Factory, output: str
) -> None:
    """Blank or insight-only answers raise; the old spec stays."""
    org_id, bud_id = await _bud(
        pg_session_factory, status=BUDStatus.TECH_ARCH, tech_spec_md="# Old plan"
    )

    async with pg_session_factory() as db:
        with pytest.raises(UnusableAgentOutputError, match="no tech spec"):
            await handle_tech_arch_result(bud_id, org_id, output, BUDAgentTask(), db)
        await db.commit()

    assert (await _reread(pg_session_factory, bud_id)).tech_spec_md == "# Old plan"


@pytest.mark.parametrize("output", ["", 'cases: {"manual_test_cases": [oops', '["TC-1"]'])
async def test_unreadable_test_cases_keep_the_recorded_results(
    pg_session_factory: Factory, output: str
) -> None:
    """Empty, malformed or non-object JSON raises; tester results and evidence stay."""
    org_id, bud_id = await _bud(
        pg_session_factory, status=BUDStatus.TESTING, qa_manual_cases=MANUAL
    )

    async with pg_session_factory() as db:
        with pytest.raises(UnusableAgentOutputError, match="could not be read"):
            await handle_testing_result(bud_id, org_id, output, BUDAgentTask(), db)
        await db.commit()

    assert (await _reread(pg_session_factory, bud_id)).qa_manual_cases == MANUAL


async def test_readable_empty_case_lists_are_still_stored(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid answer with no cases is an answer, not a parse failure."""
    monkeypatch.setattr(agent_result_handlers, "estimate_bud_dates", _no_estimate)
    org_id, bud_id = await _bud(
        pg_session_factory, status=BUDStatus.TESTING, qa_manual_cases=MANUAL
    )
    output = '{"automation_test_cases": [], "manual_test_cases": []}'

    async with pg_session_factory() as db:
        summary = await handle_testing_result(bud_id, org_id, output, BUDAgentTask(), db)
        await db.commit()

    assert summary is not None and summary["manual_count"] == 0
    assert (await _reread(pg_session_factory, bud_id)).qa_manual_cases == []
