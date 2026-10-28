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

"""The design output fallback reports a wireframe it saved as saved.

Runs the real ``write_bud_design`` handler on Postgres, so the result shape
the fallback checks is the one the handler actually returns.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDesign, BUDDesignStatus, BUDDocument, BUDStatus
from app.models.organization import Organization
from app.services import design_output_fallback
from app.services.design_output_fallback import save_wireframe_from_output

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
DOC = "<!DOCTYPE html><html><body><h1>Refund</h1></body></html>"


async def _design_row(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """An org with a design-phase BUD and one generating design row."""
    async with factory() as db:
        org = Organization(name=f"Acme {uuid.uuid4().hex[:6]}", slug=f"a-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", status=BUDStatus.DESIGN)
        db.add(bud)
        await db.flush()
        design = BUDDesign(org_id=org.id, bud_id=bud.id, status=BUDDesignStatus.GENERATING)
        db.add(design)
        await db.commit()
        return org.id, bud.id, design.id


async def test_recovered_wireframe_is_saved_and_reported_saved(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A complete document in the reply lands READY and the fallback says so."""
    monkeypatch.setattr(design_output_fallback, "AsyncSessionLocal", pg_session_factory)
    org_id, bud_id, design_id = await _design_row(pg_session_factory)

    saved = await save_wireframe_from_output(
        f"Here it is:\n\n```html\n{DOC}\n```",
        org_id=org_id,
        bud_id=str(bud_id),
        design_id=str(design_id),
        repo_id=None,
    )

    assert saved is True
    async with pg_session_factory() as db:
        design = await db.get(BUDDesign, design_id)
    assert design is not None
    assert design.status == BUDDesignStatus.READY
    assert "<h1>Refund</h1>" in (design.design_html or "")


async def test_write_refused_by_the_handler_is_reported_unsaved(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A design id on another BUD is refused by the handler; nothing is reported saved."""
    monkeypatch.setattr(design_output_fallback, "AsyncSessionLocal", pg_session_factory)
    org_id, _bud_id, design_id = await _design_row(pg_session_factory)

    saved = await save_wireframe_from_output(
        DOC, org_id=org_id, bud_id=str(uuid.uuid4()), design_id=str(design_id), repo_id=None
    )

    assert saved is False
