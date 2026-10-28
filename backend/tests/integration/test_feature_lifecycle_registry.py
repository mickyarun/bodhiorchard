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

"""BUD-authored features in the registry: planned rows, upserts and status moves.

Discard / restore is covered in ``test_bud_restore_roundtrip.py``; this file
covers creation and the forward transitions, with the embedding model faked.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.bud import BUDStatus
from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo
from app.repositories.feature import FeatureRepository
from app.services import feature_lifecycle
from app.services.feature_lifecycle import create_planned_feature, transition_feature_for_bud
from tests.integration.scan_features_bugs_support import Factory, new_org, vec

pytestmark = pytest.mark.integration

REQUIREMENTS = """# Gift cards

Customers can buy and redeem gift cards at checkout.

## Acceptance criteria
- Buy a card
- Redeem a card
"""


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _embed(text: str) -> list[float]:
        return vec(1)

    monkeypatch.setattr(feature_lifecycle, "embedding_service", SimpleNamespace(embed=_embed))


async def _plan(
    factory: Factory, org: uuid.UUID, number: int = 12, title: str = "BUD: Gift cards"
) -> Feature:
    async with factory() as db:
        feature = await create_planned_feature(db, org, number, title, REQUIREMENTS)
        await db.commit()
        return feature


async def _move(factory: Factory, org: uuid.UUID, status: BUDStatus, number: int = 12) -> None:
    async with factory() as db:
        await transition_feature_for_bud(db, org, number, status)
        await db.commit()


async def _row(factory: Factory, org: uuid.UUID, number: int = 12) -> Feature | None:
    async with factory() as db:
        return await FeatureRepository(db, org_id=org).get_by_source_ref(
            f"BUD-{number:03d}", source="bud"
        )


async def test_a_planned_feature_is_repo_less_and_searchable(pg_session_factory: Factory) -> None:
    org = await new_org(pg_session_factory)
    feature = await _plan(pg_session_factory, org)

    async with pg_session_factory() as db:
        links = (
            await db.scalars(select(FeatureToRepo).where(FeatureToRepo.feature_id == feature.id))
        ).all()
    row = await _row(pg_session_factory, org)

    assert row is not None
    assert row.feature_title == "Feature: Gift cards"
    assert row.feature_status == "planned" and row.source == "bud"
    assert row.cluster_signature == "bud:BUD-012"
    assert row.capabilities == {"capabilities": ["Buy a card", "Redeem a card"]}
    assert "Status: PLANNED" in row.description and "Source: BUD-012" in row.description
    assert row.embedding is not None
    assert links == []


async def test_recreating_the_same_bud_updates_and_revives_the_one_row(
    pg_session_factory: Factory,
) -> None:
    org = await new_org(pg_session_factory)
    first = await _plan(pg_session_factory, org)
    await _move(pg_session_factory, org, BUDStatus.DISCARDED)

    second = await _plan(pg_session_factory, org, title="Gift cards v2")
    row = await _row(pg_session_factory, org)

    assert second.id == first.id
    assert row is not None and row.is_active is True
    assert row.feature_title == "Feature: Gift cards v2"


async def test_development_moves_a_planned_feature_in_progress(
    pg_session_factory: Factory,
) -> None:
    org = await new_org(pg_session_factory)
    await _plan(pg_session_factory, org)

    await _move(pg_session_factory, org, BUDStatus.DESIGN)
    after_design = await _row(pg_session_factory, org)
    await _move(pg_session_factory, org, BUDStatus.DEVELOPMENT)
    after_dev = await _row(pg_session_factory, org)

    assert after_design is not None and after_design.feature_status == "planned"
    assert after_dev is not None and after_dev.feature_status == "in_progress"
    assert after_dev.embedding is not None


@pytest.mark.parametrize(
    "later", [BUDStatus.TECH_ARCH, BUDStatus.DEVELOPMENT, BUDStatus.TESTING, BUDStatus.CLOSED]
)
async def test_later_moves_never_send_an_in_progress_feature_backwards(
    pg_session_factory: Factory, later: BUDStatus
) -> None:
    org = await new_org(pg_session_factory)
    await _plan(pg_session_factory, org)
    await _move(pg_session_factory, org, BUDStatus.DEVELOPMENT)

    await _move(pg_session_factory, org, later)

    row = await _row(pg_session_factory, org)
    assert row is not None and row.feature_status == "in_progress" and row.is_active


async def test_a_transition_only_touches_the_callers_org(pg_session_factory: Factory) -> None:
    mine, theirs = await new_org(pg_session_factory), await new_org(pg_session_factory)
    await _plan(pg_session_factory, mine)
    await _plan(pg_session_factory, theirs)

    await _move(pg_session_factory, mine, BUDStatus.DEVELOPMENT)
    await _move(pg_session_factory, mine, BUDStatus.DISCARDED)

    moved = await _row(pg_session_factory, mine)
    untouched = await _row(pg_session_factory, theirs)
    assert moved is not None
    assert moved.feature_status == "in_progress" and moved.is_active is False
    assert untouched is not None
    assert untouched.feature_status == "planned" and untouched.is_active is True


async def test_a_bud_without_a_feature_is_a_no_op(pg_session_factory: Factory) -> None:
    org = await new_org(pg_session_factory)
    await _move(pg_session_factory, org, BUDStatus.DEVELOPMENT, number=99)
    assert await _row(pg_session_factory, org, number=99) is None


async def test_an_embedding_failure_still_creates_the_planned_row(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(text: str) -> list[float]:
        raise RuntimeError("model missing")

    monkeypatch.setattr(feature_lifecycle, "embedding_service", SimpleNamespace(embed=_boom))
    org = await new_org(pg_session_factory)

    await _plan(pg_session_factory, org)

    row = await _row(pg_session_factory, org)
    assert row is not None and row.embedding is None and row.feature_status == "planned"
