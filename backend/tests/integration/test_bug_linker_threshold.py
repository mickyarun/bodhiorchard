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

"""Bug auto-linking against real pgvector cosine distances.

Stored embeddings are the unit vector ``vec(1)``; the bug's vector is
chosen so its distance to that is exactly the threshold, or a hair either
side. Integer components keep float4 storage exact, so "exactly at" is a
real boundary, not a rounding accident. The embedding model is faked.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bug import Bug, BugSeverity, BugType
from app.services import bug_linker
from app.services.bug_linker import (
    AUTO_LINK_FEATURE_THRESHOLD,
    AUTO_LINK_THRESHOLD,
    embed_and_link_bug,
)
from tests.integration.scan_features_bugs_support import (
    Factory,
    cosine_distance,
    new_bud,
    new_feature,
    new_member,
    new_org,
    vec,
)

pytestmark = pytest.mark.integration

ANCHOR = vec(1)
# Distances to ANCHOR: 3/5 → 0.40 exactly; 13/20 → 0.35 exactly.
BUD_AT = vec(3, 4)
BUD_BELOW = vec(301, 400)
BUD_ABOVE = vec(299, 400)
FEATURE_AT = vec(13, 15, 2, 1, 1)
FEATURE_BELOW = vec(1301, 1500, 200, 100, 100)
FEATURE_ABOVE = vec(1299, 1500, 200, 100, 100)


def test_the_boundary_vectors_sit_where_the_tests_claim() -> None:
    """Guard the fixtures: exact at, then strictly either side of each threshold."""
    assert cosine_distance(BUD_AT, ANCHOR) == AUTO_LINK_THRESHOLD
    assert cosine_distance(BUD_BELOW, ANCHOR) < AUTO_LINK_THRESHOLD
    assert cosine_distance(BUD_ABOVE, ANCHOR) > AUTO_LINK_THRESHOLD
    assert cosine_distance(FEATURE_AT, ANCHOR) == AUTO_LINK_FEATURE_THRESHOLD
    assert cosine_distance(FEATURE_BELOW, ANCHOR) < AUTO_LINK_FEATURE_THRESHOLD
    assert cosine_distance(FEATURE_ABOVE, ANCHOR) > AUTO_LINK_FEATURE_THRESHOLD


def _embed_as(monkeypatch: pytest.MonkeyPatch, vector: list[float] | Exception) -> None:
    """Make the embedding model return ``vector`` (or raise it)."""

    async def _embed(text: str) -> list[float]:
        if isinstance(vector, Exception):
            raise vector
        return vector

    monkeypatch.setattr(bug_linker, "embedding_service", SimpleNamespace(embed=_embed))


async def _link(
    factory: Factory,
    org: uuid.UUID,
    *,
    bug_type: BugType = BugType.TESTING,
    bud_id: uuid.UUID | None = None,
) -> tuple[object | None, Bug]:
    """File a bug in ``org``, run the linker, and return (match, bug as stored)."""
    reporter = await new_member(factory, org)
    async with factory() as db:
        bug = Bug(
            org_id=org,
            bug_number=1,
            title="Checkout button does nothing",
            description="Clicking pay is a no-op",
            severity=BugSeverity.HIGH,
            bug_type=bug_type,
            bud_id=bud_id,
            reporter_id=reporter,
        )
        db.add(bug)
        await db.flush()
        match = await embed_and_link_bug(db, org, bug)
        await db.commit()
        bug_id = bug.id
    async with factory() as db:
        stored = await _reload(db, bug_id)
    return match, stored


async def _reload(db: AsyncSession, bug_id: uuid.UUID) -> Bug:
    stored = await db.get(Bug, bug_id)
    assert stored is not None
    return stored


@pytest.mark.parametrize(
    ("bug_vector", "links"),
    [(BUD_AT, True), (BUD_BELOW, True), (BUD_ABOVE, False)],
    ids=["exactly-at-0.40", "just-below", "just-above"],
)
async def test_testing_bug_links_to_a_bud_up_to_and_including_the_threshold(
    pg_session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
    bug_vector: list[float],
    links: bool,
) -> None:
    org = await new_org(pg_session_factory)
    bud = await new_bud(pg_session_factory, org, 1, embedding=ANCHOR)
    _embed_as(monkeypatch, bug_vector)

    match, stored = await _link(pg_session_factory, org)

    assert stored.bud_id == (bud if links else None)
    assert (getattr(match, "id", None) == bud) is links
    assert stored.embedding is not None


@pytest.mark.parametrize(
    ("bug_vector", "links"),
    [(FEATURE_AT, True), (FEATURE_BELOW, True), (FEATURE_ABOVE, False)],
    ids=["exactly-at-0.35", "just-below", "just-above"],
)
async def test_production_bug_links_to_a_feature_up_to_and_including_its_threshold(
    pg_session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
    bug_vector: list[float],
    links: bool,
) -> None:
    org = await new_org(pg_session_factory)
    feature = await new_feature(pg_session_factory, org, "Checkout", embedding=ANCHOR)
    _embed_as(monkeypatch, bug_vector)

    _, stored = await _link(pg_session_factory, org, bug_type=BugType.PRODUCTION)

    assert stored.feature_id == (feature if links else None)
    assert stored.bud_id is None
    assert stored.bug_type == BugType.PRODUCTION


async def test_another_orgs_identical_bud_is_never_linked(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = await new_org(pg_session_factory)
    theirs = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, theirs, 1, embedding=ANCHOR)
    await new_bud(pg_session_factory, mine, 1, embedding=BUD_ABOVE)
    _embed_as(monkeypatch, ANCHOR)

    match, stored = await _link(pg_session_factory, mine)

    assert match is None
    assert stored.bud_id is None


async def test_another_orgs_identical_feature_is_never_linked(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = await new_org(pg_session_factory)
    theirs = await new_org(pg_session_factory)
    await new_feature(pg_session_factory, theirs, "Their checkout", embedding=ANCHOR)
    _embed_as(monkeypatch, ANCHOR)

    match, stored = await _link(pg_session_factory, mine, bug_type=BugType.PRODUCTION)

    assert match is None
    assert stored.feature_id is None


async def test_a_deactivated_feature_is_never_linked(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_feature(pg_session_factory, org, "Old checkout", embedding=ANCHOR, active=False)
    _embed_as(monkeypatch, ANCHOR)

    _, stored = await _link(pg_session_factory, org, bug_type=BugType.PRODUCTION)

    assert stored.feature_id is None


async def test_a_production_bug_does_not_fall_back_to_a_bud(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, org, 1, embedding=ANCHOR)
    _embed_as(monkeypatch, ANCHOR)

    match, stored = await _link(pg_session_factory, org, bug_type=BugType.PRODUCTION)

    assert match is None
    assert stored.bud_id is None and stored.feature_id is None


async def test_a_testing_bug_ignores_features_even_when_identical(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_feature(pg_session_factory, org, "Checkout", embedding=ANCHOR)
    _embed_as(monkeypatch, ANCHOR)

    _, stored = await _link(pg_session_factory, org)

    assert stored.feature_id is None
    assert stored.bug_type == BugType.TESTING


async def test_a_manual_bud_link_is_kept_even_when_another_bud_is_closer(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    chosen = await new_bud(pg_session_factory, org, 1, embedding=BUD_ABOVE)
    await new_bud(pg_session_factory, org, 2, embedding=ANCHOR)
    _embed_as(monkeypatch, ANCHOR)

    match, stored = await _link(pg_session_factory, org, bud_id=chosen)

    assert match is None
    assert stored.bud_id == chosen
    assert stored.embedding is not None


async def test_buds_without_embeddings_are_skipped(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, org, 1, embedding=None)
    _embed_as(monkeypatch, ANCHOR)

    match, stored = await _link(pg_session_factory, org)

    assert match is None and stored.bud_id is None


async def test_the_closest_of_several_buds_wins(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, org, 1, embedding=BUD_AT)
    nearest = await new_bud(pg_session_factory, org, 2, embedding=BUD_BELOW)
    _embed_as(monkeypatch, ANCHOR)

    _, stored = await _link(pg_session_factory, org)

    assert stored.bud_id == nearest


async def test_an_embedding_failure_leaves_the_bug_unlinked_and_unembedded(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, org, 1, embedding=ANCHOR)
    _embed_as(monkeypatch, RuntimeError("model not loaded"))

    match, stored = await _link(pg_session_factory, org)

    assert match is None
    assert stored.bud_id is None
    assert stored.embedding is None
