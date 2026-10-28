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

"""The Jira dedup query on pgvector: org-scoped, embedding-only, exclusions.

A Jira issue must never be skipped as a duplicate of another org's BUD,
which would also leak that BUD's number into the import notes.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.bud import BUDDocument, BUDStatus
from app.models.organization import Organization
from app.services.jira_dedup import check_semantic_duplicate
from tests.integration.settings_support import Factory

pytestmark = pytest.mark.integration

DIMS = 384


def _axis(index: int) -> list[float]:
    """A unit vector along one axis; two different axes are distance 1."""
    vector = [0.0] * DIMS
    vector[index] = 1.0
    return vector


async def _org_with_buds(factory: Factory, *embeddings: list[float] | None) -> list[uuid.UUID]:
    """A fresh org; returns ``[org_id, bud_id...]``."""
    async with factory() as db:
        org = Organization(name="Dedup", slug=f"dd-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        ids = [org.id]
        for number, embedding in enumerate(embeddings, start=1):
            bud = BUDDocument(
                org_id=org.id,
                bud_number=number,
                title=f"BUD {number}",
                status=BUDStatus.BUD,
                embedding=embedding,
            )
            db.add(bud)
            await db.flush()
            ids.append(bud.id)
        await db.commit()
        return ids


async def test_an_identical_bud_in_another_org_is_not_a_duplicate(
    pg_session_factory: Factory,
) -> None:
    other_org, _ = await _org_with_buds(pg_session_factory, _axis(0))
    (org_id,) = await _org_with_buds(pg_session_factory)

    async with pg_session_factory() as db:
        mine = await check_semantic_duplicate(db, org_id, _axis(0))
        theirs = await check_semantic_duplicate(db, other_org, _axis(0))

    assert (mine.is_duplicate, mine.matched_bud_id) == (False, None)
    assert mine.note == "No existing BUDs with embeddings"
    assert theirs.is_duplicate is True


async def test_buds_without_embeddings_are_ignored(pg_session_factory: Factory) -> None:
    org_id, _ = await _org_with_buds(pg_session_factory, None)
    async with pg_session_factory() as db:
        result = await check_semantic_duplicate(db, org_id, _axis(0))
    assert result.matched_bud_id is None
    assert result.distance is None


async def test_the_nearest_wins_and_exclusions_are_honoured(pg_session_factory: Factory) -> None:
    org_id, exact, _far = await _org_with_buds(pg_session_factory, _axis(0), _axis(1))

    async with pg_session_factory() as db:
        nearest = await check_semantic_duplicate(db, org_id, _axis(0))
        without_exact = await check_semantic_duplicate(
            db, org_id, _axis(0), exclude_bud_ids={exact}
        )

    assert (nearest.is_duplicate, nearest.matched_bud_id) == (True, exact)
    assert without_exact.is_duplicate is False
    assert without_exact.needs_review is False
    # The other BUD is orthogonal: distance 1, so the candidate counts as new.
    assert without_exact.distance == 1.0
    assert without_exact.matched_bud_id is None
