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

"""Bug auto-linking at the cosine-distance thresholds, on real pgvector.

A testing bug links to a BUD up to and including distance 0.40; a
production bug links to a feature up to and including 0.35. Each boundary
is checked exactly at, just below and just above. The model is faked.
"""

from __future__ import annotations

import pytest

from app.models.bug import BugType
from app.services.bug_linker import AUTO_LINK_FEATURE_THRESHOLD, AUTO_LINK_THRESHOLD
from tests.integration.bug_linker_support import (
    ANCHOR,
    BUD_ABOVE,
    BUD_AT,
    BUD_BELOW,
    FEATURE_ABOVE,
    FEATURE_AT,
    FEATURE_BELOW,
    embed_as,
    link,
)
from tests.integration.scan_features_bugs_support import (
    Factory,
    cosine_distance,
    new_bud,
    new_feature,
    new_org,
)

pytestmark = pytest.mark.integration


def test_the_boundary_vectors_sit_where_the_tests_claim() -> None:
    """Guard the fixtures: exact at, then strictly either side of each threshold."""
    assert cosine_distance(BUD_AT, ANCHOR) == AUTO_LINK_THRESHOLD
    assert cosine_distance(BUD_BELOW, ANCHOR) < AUTO_LINK_THRESHOLD
    assert cosine_distance(BUD_ABOVE, ANCHOR) > AUTO_LINK_THRESHOLD
    assert cosine_distance(FEATURE_AT, ANCHOR) == AUTO_LINK_FEATURE_THRESHOLD
    assert cosine_distance(FEATURE_BELOW, ANCHOR) < AUTO_LINK_FEATURE_THRESHOLD
    assert cosine_distance(FEATURE_ABOVE, ANCHOR) > AUTO_LINK_FEATURE_THRESHOLD


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
    embed_as(monkeypatch, bug_vector)

    match, stored = await link(pg_session_factory, org)

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
    embed_as(monkeypatch, bug_vector)

    _, stored = await link(pg_session_factory, org, bug_type=BugType.PRODUCTION)

    assert stored.feature_id == (feature if links else None)
    assert stored.bud_id is None
    assert stored.bug_type == BugType.PRODUCTION
