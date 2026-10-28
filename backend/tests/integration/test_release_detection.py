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

"""Release-stage detection when a PR merges into a stage branch.

Fast path: the merged PR is a BUD branch (``bud_id`` on its row). SHA walk:
a release PR with no BUD, whose commits are matched to BUDs through
``merge_commit_sha`` and dev-activity commits. The GitHub commit list and
the post-close side effects are faked; everything else hits Postgres.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.models.bud import BUDDocument, BUDStatus
from app.models.tracked_repository import TrackedRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.services.github_webhook_handler import handle_github_event
from tests.integration.github_webhook_support import merged_pr_payload
from tests.integration.release_detection_support import (
    ReleaseWorld,
    add_dev_commit,
    add_pr,
    fake_github_commits,
    stub_close_side_effects,
)
from tests.integration.scan_features_bugs_support import Factory, new_bud

pytestmark = pytest.mark.integration


async def _deliver(world: ReleaseWorld, *, number: int, base: str) -> None:
    """Run a merged ``pull_request.closed`` for PR ``number`` through the handler."""
    payload = json.loads(merged_pr_payload(world.full_name, number=number, base=base))
    async with world.factory() as db:
        repo = await db.get(TrackedRepository, world.repo)
        assert repo is not None
        await handle_github_event(
            org_id=world.org, repo=repo, event_type="pull_request", payload=payload, db=db
        )


async def _events(world: ReleaseWorld, bud: uuid.UUID, kind: str) -> list[dict[str, object]]:
    async with world.factory() as db:
        rows = await BUDTimelineRepository(db, org_id=world.org).list_for_bud_by_event_type(
            bud, kind
        )
        return [r.detail or {} for r in rows]


async def _status(world: ReleaseWorld, bud: uuid.UUID) -> BUDStatus:
    async with world.factory() as db:
        row = await db.get(BUDDocument, bud)
        assert row is not None
        return row.status


async def test_fast_path_records_prod_once_and_closes_a_bud_whose_repos_all_shipped(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed = stub_close_side_effects(monkeypatch)
    commits = fake_github_commits(monkeypatch, [])
    world = await ReleaseWorld.create(pg_session_factory)
    bud = await world.bud_in(BUDStatus.UAT, impacted=[world.repo])
    await add_pr(world, number=5, bud=bud)

    await _deliver(world, number=5, base="main")
    await _deliver(world, number=5, base="main")

    prod = await _events(world, bud, "merged_to_prod")
    assert len(prod) == 1
    assert prod[0]["release_pr_number"] == 5 and prod[0]["repo_id"] == str(world.repo)
    assert await _status(world, bud) == BUDStatus.CLOSED
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

    await _deliver(world, number=6, base="main")

    assert len(await _events(world, bud, "merged_to_prod")) == 1
    assert await _status(world, bud) == BUDStatus.PROD
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

    await _deliver(world, number=8, base="main")

    assert len(await _events(world, bud, "merged_to_prod")) == 1
    assert await _status(world, bud) == status
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

    await _deliver(world, number=9, base=base)

    for kind in ("merged_to_develop", "merged_to_uat", "merged_to_prod"):
        assert len(await _events(world, bud, kind)) == (1 if kind == stage else 0)


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

    await _deliver(world, number=12, base="main")
    await _deliver(world, number=12, base="main")

    first = await _events(world, squashed, "merged_to_prod")
    second = await _events(world, merged, "merged_to_prod")
    assert len(first) == 1 and len(second) == 1
    assert [c["sha"] for c in second[0]["matched_commits"]] == ["c" * 40, "d" * 40]  # type: ignore[union-attr]
    assert second[0]["release_pr_number"] == 12
    assert commits.calls == 2


async def test_sha_walk_never_matches_another_orgs_commits(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_close_side_effects(monkeypatch)
    world = await ReleaseWorld.create(pg_session_factory)
    other = await ReleaseWorld.create(pg_session_factory)
    their_bud = await other.bud_in(BUDStatus.UAT, impacted=[])
    await add_pr(other, number=3, bud=their_bud, merge_sha="f" * 40, state="merged")
    await add_dev_commit(other, bud=their_bud, sha="9" * 40)
    await add_pr(world, number=4, bud=None)
    fake_github_commits(monkeypatch, ["f" * 40, "9" * 40])

    await _deliver(world, number=4, base="main")

    assert await _events(other, their_bud, "merged_to_prod") == []


async def test_a_github_failure_does_not_break_pr_bookkeeping(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_close_side_effects(monkeypatch)
    fake_github_commits(monkeypatch, RuntimeError("GitHub 502"))
    world = await ReleaseWorld.create(pg_session_factory)
    bud = await new_bud(pg_session_factory, world.org, 77, status=BUDStatus.UAT)
    pr = await add_pr(world, number=13, bud=None)

    await _deliver(world, number=13, base="main")

    assert await _events(world, bud, "merged_to_prod") == []
    assert (await pr.reload()).state == "merged"
