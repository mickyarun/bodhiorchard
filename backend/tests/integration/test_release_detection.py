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

"""Release-stage detection on the fast path: a BUD-branch PR merges into a stage branch.

The PR row already carries ``bud_id``, so no GitHub call is made. The
post-close side effects are faked; everything else hits Postgres.
"""

from __future__ import annotations

import pytest

from app.models.bud import BUDStatus
from tests.integration.release_detection_support import (
    ReleaseWorld,
    add_pr,
    bud_status,
    deliver,
    fake_github_commits,
    stub_close_side_effects,
    timeline,
)
from tests.integration.scan_features_bugs_support import Factory

pytestmark = pytest.mark.integration


async def test_fast_path_records_prod_once_and_closes_a_bud_whose_repos_all_shipped(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = stub_close_side_effects(monkeypatch)
    commits = fake_github_commits(monkeypatch, [])
    world = await ReleaseWorld.create(pg_session_factory)
    bud = await world.bud_in(BUDStatus.UAT, impacted=[world.repo])
    await add_pr(world, number=5, bud=bud)

    await deliver(world, number=5, base="main")
    await deliver(world, number=5, base="main")

    prod = await timeline(world.factory, bud, "merged_to_prod")
    assert len(prod) == 1
    assert prod[0]["release_pr_number"] == 5 and prod[0]["repo_id"] == str(world.repo)
    assert await bud_status(world.factory, bud) == BUDStatus.CLOSED
    assert closed == [bud]
    assert commits.calls == 0


async def test_a_bud_waits_for_every_impacted_repo_before_closing(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = stub_close_side_effects(monkeypatch)
    fake_github_commits(monkeypatch, [])
    world = await ReleaseWorld.create(pg_session_factory)
    other_repo = await world.extra_repo()
    bud = await world.bud_in(BUDStatus.PROD, impacted=[world.repo, other_repo])
    await add_pr(world, number=6, bud=bud)

    await deliver(world, number=6, base="main")

    assert len(await timeline(world.factory, bud, "merged_to_prod")) == 1
    assert await bud_status(world.factory, bud) == BUDStatus.PROD
    assert closed == []


@pytest.mark.parametrize("status", [BUDStatus.TESTING, BUDStatus.CLOSED])
async def test_only_uat_or_prod_buds_auto_close(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch, status: BUDStatus
) -> None:
    closed = stub_close_side_effects(monkeypatch)
    fake_github_commits(monkeypatch, [])
    world = await ReleaseWorld.create(pg_session_factory)
    bud = await world.bud_in(status, impacted=[world.repo])
    await add_pr(world, number=8, bud=bud)

    await deliver(world, number=8, base="main")

    assert len(await timeline(world.factory, bud, "merged_to_prod")) == 1
    assert await bud_status(world.factory, bud) == status
    assert closed == []


@pytest.mark.parametrize(
    ("base", "uat_enabled", "stage"),
    [
        ("develop", True, "merged_to_develop"),
        ("release/uat", True, "merged_to_uat"),
        ("release/uat", False, None),
        ("feature/other", True, None),
    ],
)
async def test_the_base_branch_and_uat_toggle_pick_the_stage(
    pg_session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
    base: str,
    uat_enabled: bool,
    stage: str | None,
) -> None:
    stub_close_side_effects(monkeypatch)
    fake_github_commits(monkeypatch, [])
    world = await ReleaseWorld.create(pg_session_factory, uat_enabled=uat_enabled)
    bud = await world.bud_in(BUDStatus.TESTING, impacted=[world.repo])
    await add_pr(world, number=9, bud=bud)

    await deliver(world, number=9, base=base)

    for kind in ("merged_to_develop", "merged_to_uat", "merged_to_prod"):
        assert len(await timeline(world.factory, bud, kind)) == (1 if kind == stage else 0)
