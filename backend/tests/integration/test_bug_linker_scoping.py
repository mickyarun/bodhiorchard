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

"""Which BUDs and features the bug linker may pick, on real pgvector.

Another org's rows, deactivated features and the other pool are never
candidates; a manual link is never overwritten; an embedding failure links
nothing. The model is faked.
"""

from __future__ import annotations

import pytest

from app.models.bug import BugType
from tests.integration.bug_linker_support import (
    ANCHOR,
    BUD_ABOVE,
    BUD_AT,
    BUD_BELOW,
    embed_as,
    link,
)
from tests.integration.scan_features_bugs_support import Factory, new_bud, new_feature, new_org

pytestmark = pytest.mark.integration


async def test_another_orgs_identical_bud_is_never_linked(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = await new_org(pg_session_factory)
    theirs = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, theirs, 1, embedding=ANCHOR)
    await new_bud(pg_session_factory, mine, 1, embedding=BUD_ABOVE)
    embed_as(monkeypatch, ANCHOR)

    match, stored = await link(pg_session_factory, mine)

    assert match is None
    assert stored.bud_id is None


async def test_another_orgs_identical_feature_is_never_linked(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = await new_org(pg_session_factory)
    theirs = await new_org(pg_session_factory)
    await new_feature(pg_session_factory, theirs, "Their checkout", embedding=ANCHOR)
    embed_as(monkeypatch, ANCHOR)

    match, stored = await link(pg_session_factory, mine, bug_type=BugType.PRODUCTION)

    assert match is None
    assert stored.feature_id is None


async def test_a_deactivated_feature_is_never_linked(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_feature(pg_session_factory, org, "Old checkout", embedding=ANCHOR, active=False)
    embed_as(monkeypatch, ANCHOR)

    _, stored = await link(pg_session_factory, org, bug_type=BugType.PRODUCTION)

    assert stored.feature_id is None


async def test_a_production_bug_does_not_fall_back_to_a_bud(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, org, 1, embedding=ANCHOR)
    embed_as(monkeypatch, ANCHOR)

    match, stored = await link(pg_session_factory, org, bug_type=BugType.PRODUCTION)

    assert match is None
    assert stored.bud_id is None and stored.feature_id is None


async def test_a_testing_bug_ignores_features_even_when_identical(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_feature(pg_session_factory, org, "Checkout", embedding=ANCHOR)
    embed_as(monkeypatch, ANCHOR)

    _, stored = await link(pg_session_factory, org)

    assert stored.feature_id is None
    assert stored.bug_type == BugType.TESTING


async def test_a_manual_bud_link_is_kept_even_when_another_bud_is_closer(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    chosen = await new_bud(pg_session_factory, org, 1, embedding=BUD_ABOVE)
    await new_bud(pg_session_factory, org, 2, embedding=ANCHOR)
    embed_as(monkeypatch, ANCHOR)

    match, stored = await link(pg_session_factory, org, bud_id=chosen)

    assert match is None
    assert stored.bud_id == chosen
    assert stored.embedding is not None


async def test_buds_without_embeddings_are_skipped(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, org, 1, embedding=None)
    embed_as(monkeypatch, ANCHOR)

    match, stored = await link(pg_session_factory, org)

    assert match is None and stored.bud_id is None


async def test_the_closest_of_several_buds_wins(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, org, 1, embedding=BUD_AT)
    nearest = await new_bud(pg_session_factory, org, 2, embedding=BUD_BELOW)
    embed_as(monkeypatch, ANCHOR)

    _, stored = await link(pg_session_factory, org)

    assert stored.bud_id == nearest


async def test_an_embedding_failure_leaves_the_bug_unlinked_and_unembedded(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await new_org(pg_session_factory)
    await new_bud(pg_session_factory, org, 1, embedding=ANCHOR)
    embed_as(monkeypatch, RuntimeError("model not loaded"))

    match, stored = await link(pg_session_factory, org)

    assert match is None
    assert stored.bud_id is None
    assert stored.embedding is None
