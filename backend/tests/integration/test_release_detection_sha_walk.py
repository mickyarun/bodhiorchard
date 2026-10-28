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

"""Release-stage detection by walking a release PR's commits.

A release PR with no BUD of its own is matched to BUDs through
``merge_commit_sha`` and dev-activity commits. The GitHub commit list is
faked; timeline events are read without an org filter so a leak into
another org would show.
"""

from __future__ import annotations

import pytest

from app.models.bud import BUDStatus
from tests.integration.release_detection_support import (
    ReleaseWorld,
    add_dev_commit,
    add_pr,
    deliver,
    fake_github_commits,
    stub_close_side_effects,
    timeline,
)
from tests.integration.scan_features_bugs_support import Factory

pytestmark = pytest.mark.integration


async def test_sha_walk_finds_each_bud_once_through_merge_and_dev_commits(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_close_side_effects(monkeypatch)
    world = await ReleaseWorld.create(pg_session_factory)
    squashed = await world.bud_in(BUDStatus.UAT, impacted=[])
    merged = await world.bud_in(BUDStatus.UAT, impacted=[])
    await add_pr(world, number=11, bud=squashed, merge_sha="a" * 40, state="merged")
    await add_dev_commit(world, bud=merged, sha="c" * 40)
    await add_dev_commit(world, bud=merged, sha="d" * 40)
    await add_pr(world, number=12, bud=None)
    commits = fake_github_commits(monkeypatch, ["a" * 40, "c" * 40, "d" * 40, "e" * 40])

    await deliver(world, number=12, base="main")
    await deliver(world, number=12, base="main")

    first = await timeline(pg_session_factory, squashed, "merged_to_prod")
    second = await timeline(pg_session_factory, merged, "merged_to_prod")
    assert len(first) == 1 and len(second) == 1
    assert [c["sha"] for c in second[0]["matched_commits"]] == ["c" * 40, "d" * 40]
    assert second[0]["release_pr_number"] == 12
    assert commits.calls == 2


async def test_sha_walk_never_matches_another_orgs_commits(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the releasing org's own BUD gets the event, though both own the same SHAs."""
    stub_close_side_effects(monkeypatch)
    world = await ReleaseWorld.create(pg_session_factory)
    other = await ReleaseWorld.create(pg_session_factory)
    their_bud = await other.bud_in(BUDStatus.UAT, impacted=[])
    await add_pr(other, number=3, bud=their_bud, merge_sha="f" * 40, state="merged")
    await add_dev_commit(other, bud=their_bud, sha="9" * 40)
    own_bud = await world.bud_in(BUDStatus.UAT, impacted=[])
    await add_pr(world, number=5, bud=own_bud, merge_sha="f" * 40, state="merged")
    await add_pr(world, number=4, bud=None)
    fake_github_commits(monkeypatch, ["f" * 40, "9" * 40])

    await deliver(world, number=4, base="main")

    assert await timeline(pg_session_factory, their_bud, "merged_to_prod") == []
    own = await timeline(pg_session_factory, own_bud, "merged_to_prod")
    assert [e["release_pr_number"] for e in own] == [4]


async def test_a_github_failure_records_nothing_but_keeps_pr_bookkeeping(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_close_side_effects(monkeypatch)
    fake_github_commits(monkeypatch, RuntimeError("GitHub 502"))
    world = await ReleaseWorld.create(pg_session_factory)
    bud = await world.bud_in(BUDStatus.UAT, impacted=[])
    await add_dev_commit(world, bud=bud, sha="7" * 40)
    pr = await add_pr(world, number=13, bud=None)

    await deliver(world, number=13, base="main")

    assert await timeline(pg_session_factory, bud, "merged_to_prod") == []
    assert (await pr.reload()).state == "merged"
