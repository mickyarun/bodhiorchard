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

"""Org, repo, BUD and PR setup plus GitHub fakes for the release-detection tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.models.bud import BUDDocument, BUDStatus
from app.models.dev_activity import DevActivityLog
from app.models.pull_request import PRState, PullRequest
from app.services import bud_closure, release_detection
from tests.integration.scan_features_bugs_support import Factory, new_bud, new_org, new_repo

BRANCHES = {"main_branch": "main", "develop_branch": "develop", "uat_branch": "release/uat"}


@dataclass
class ReleaseWorld:
    """One org tracking one GitHub repo with develop, UAT and main stage branches."""

    factory: Factory
    org: uuid.UUID
    repo: uuid.UUID
    full_name: str
    next_bud: int = 1

    @classmethod
    async def create(cls, factory: Factory, *, uat_enabled: bool = True) -> ReleaseWorld:
        """A fresh org (UAT toggle as given) and its tracked repo."""
        org = await new_org(factory, config={"bud_stages": {"uat_enabled": uat_enabled}})
        full_name = f"acme/{uuid.uuid4().hex[:12]}"
        repo = await new_repo(factory, org, github_repo_full_name=full_name, **BRANCHES)
        return cls(factory=factory, org=org, repo=repo, full_name=full_name)

    async def extra_repo(self) -> uuid.UUID:
        """A second tracked repo in the same org."""
        return await new_repo(self.factory, self.org, **BRANCHES)

    async def bud_in(self, status: BUDStatus, *, impacted: list[uuid.UUID]) -> uuid.UUID:
        """A BUD in ``status`` whose impacted repos are ``impacted``."""
        number, self.next_bud = self.next_bud, self.next_bud + 1
        return await new_bud(
            self.factory,
            self.org,
            number,
            status=status,
            impacted_repos=[{"repo_id": str(r)} for r in impacted],
        )


@dataclass
class PrHandle:
    """A stored PR row that can be re-read after the handler ran."""

    factory: Factory
    id: uuid.UUID

    async def reload(self) -> PullRequest:
        """The row as it is now in the database."""
        async with self.factory() as db:
            row = await db.get(PullRequest, self.id)
            assert row is not None
            return row


async def add_pr(
    world: ReleaseWorld,
    *,
    number: int,
    bud: uuid.UUID | None,
    merge_sha: str | None = None,
    state: str = "open",
) -> PrHandle:
    """A tracked PR whose GitHub id matches ``merged_pr_payload(number=number)``."""
    async with world.factory() as db:
        pr = PullRequest(
            org_id=world.org,
            bud_id=bud,
            repo_id=world.repo,
            github_pr_number=number,
            github_pr_id=900_000 + number,
            github_repo_full_name=world.full_name,
            title=f"PR {number}",
            html_url=f"https://github.com/{world.full_name}/pull/{number}",
            head_branch=f"bud-{number}",
            base_branch="main",
            state=PRState(state),
            author_github_login="octo",
            merge_commit_sha=merge_sha,
        )
        db.add(pr)
        await db.commit()
        return PrHandle(world.factory, pr.id)


async def add_dev_commit(world: ReleaseWorld, *, bud: uuid.UUID, sha: str) -> None:
    """A dev-activity commit row tying ``sha`` to ``bud``."""
    async with world.factory() as db:
        db.add(
            DevActivityLog(
                org_id=world.org,
                bud_id=bud,
                repo_id=world.repo,
                event_type="commit",
                source="hook",
                commit_sha=sha,
            )
        )
        await db.commit()


@dataclass
class FakeCommits:
    """Counts how often the release PR's commits were fetched."""

    calls: int = 0


def fake_github_commits(
    monkeypatch: pytest.MonkeyPatch, shas: list[str] | Exception
) -> FakeCommits:
    """Serve ``shas`` as the release PR's commits (or raise) without calling GitHub."""
    seen = FakeCommits()

    class _Client:
        def __init__(self, token: str) -> None:
            pass

        async def get_pr_commits(self, full_name: str, number: int) -> list[dict[str, Any]]:
            seen.calls += 1
            if isinstance(shas, Exception):
                raise shas
            return [{"sha": s, "commit": {"message": f"work {s[:4]}\n\nbody"}} for s in shas]

    async def _token(org: object) -> str:
        return "installation-token"

    monkeypatch.setattr(release_detection, "GitHubClient", _Client)
    monkeypatch.setattr(release_detection, "get_installation_token", _token)
    return seen


def stub_close_side_effects(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Record BUDs handed to the post-close pipeline instead of running agents."""
    closed: list[uuid.UUID] = []

    async def _on_closed(db: object, org_id: uuid.UUID, bud: BUDDocument) -> None:
        closed.append(bud.id)

    monkeypatch.setattr(bud_closure, "on_bud_closed", _on_closed)
    return closed
