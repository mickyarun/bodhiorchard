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

"""A BUD's delivery state, written the way GitHub and the QA agent leave it.

In a real install the GitHub webhook records PRs and release merges, and the
QA agent writes manual test cases. The e2e stack has no GitHub and fakes the
agents, so these helpers write the same rows: tracked repos, the BUD's
impacted repos (confirmed for review), pull requests, manual cases and
``merged_to_uat`` / ``merged_to_prod`` timeline events.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDTimelineEventType
from app.models.pull_request import PRState, PullRequest
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.repositories.bud import BUDRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.bud_timeline import record_event
from tests.e2e_stack.specs_delivery import (
    DeliverySpec,
    ManualCasesSpec,
    PullRequestSpec,
    ReleaseSpec,
    RepoSpec,
    SeededRepo,
)

_RELEASE_EVENT = {
    "uat": BUDTimelineEventType.MERGED_TO_UAT,
    "prod": BUDTimelineEventType.MERGED_TO_PROD,
}


async def _bud(db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID) -> BUDDocument:
    bud = await BUDRepository(db, org_id=org_id).get_by_id(bud_id)
    if bud is None or bud.org_id != org_id:
        raise HTTPException(status_code=404, detail="no such BUD in this org")
    return bud


async def _repos(
    db: AsyncSession, org_id: uuid.UUID, ids: list[uuid.UUID]
) -> dict[uuid.UUID, TrackedRepository]:
    repos = TrackedRepoRepository(db, org_id=org_id)
    found: dict[uuid.UUID, TrackedRepository] = {}
    for repo_id in ids:
        repo = await repos.get_by_id(repo_id)
        if repo is None or repo.org_id != org_id:
            raise HTTPException(status_code=404, detail=f"no repo {repo_id} in this org")
        found[repo_id] = repo
    return found


async def add_repo(db: AsyncSession, org_id: uuid.UUID, spec: RepoSpec) -> SeededRepo:
    """A tracked repo with main, develop and uat branches (no checkout needed)."""
    repo = TrackedRepository(
        org_id=org_id,
        path=str(Path.home() / "repos" / spec.name),
        name=spec.name,
        status=RepoStatus.ACTIVE,
        main_branch="main",
        develop_branch="develop",
        uat_branch="uat",
        github_repo_full_name=f"e2e/{spec.name}",
    )
    db.add(repo)
    await db.commit()
    return SeededRepo(id=repo.id, name=repo.name)


def _pull_request(
    org_id: uuid.UUID, bud_id: uuid.UUID, repo: TrackedRepository, spec: PullRequestSpec
) -> PullRequest:
    state = PRState(spec.state)
    return PullRequest(
        org_id=org_id,
        bud_id=bud_id,
        repo_id=repo.id,
        github_pr_number=spec.number,
        # Unique per org; derived so a test can't collide with another's PR.
        github_pr_id=uuid.uuid4().int % 10**15,
        github_repo_full_name=repo.github_repo_full_name or repo.name,
        title=spec.title,
        html_url=f"https://github.invalid/{repo.github_repo_full_name}/pull/{spec.number}",
        head_branch=f"feature/pr-{spec.number}",
        base_branch=repo.develop_branch or "develop",
        state=state,
        merged_at=datetime.now(UTC) if state == PRState.MERGED else None,
        author_github_login="e2e-dev",
    )


async def set_delivery(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID, spec: DeliverySpec
) -> None:
    """Impacted repos (confirmed for review) and their PRs."""
    bud = await _bud(db, org_id, bud_id)
    repos = await _repos(db, org_id, [*spec.repo_ids, *(pr.repo_id for pr in spec.pull_requests)])
    impacted = [repos[rid] for rid in spec.repo_ids]
    bud.impacted_repos = [{"repo_id": str(r.id), "repo_name": r.name} for r in impacted]
    metadata: dict[str, Any] = dict(bud.metadata_ or {})
    metadata["confirmed_repos"] = [{"repo_path": r.path, "repo_name": r.name} for r in impacted]
    bud.metadata_ = metadata
    for pr in spec.pull_requests:
        db.add(_pull_request(org_id, bud_id, repos[pr.repo_id], pr))
    await db.commit()


async def set_manual_cases(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID, spec: ManualCasesSpec
) -> None:
    """Pending manual cases in the shape the QA agent writes."""
    bud = await _bud(db, org_id, bud_id)
    bud.qa_manual_cases = [
        {
            "id": case.id, "title": case.title, "description": case.title, "preconditions": "",
            "steps": ["Open the screen", "Do the thing"], "expected_result": "It works",
            "priority": "high", "category": "functional", "result": "pending",
            "tester_name": None, "tested_at": None,
        }
        for case in spec.cases
    ]  # fmt: skip
    await db.commit()


async def record_release(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID, spec: ReleaseSpec
) -> None:
    """A release PR merged into the stage's branch, as release detection records it."""
    await _bud(db, org_id, bud_id)
    repo = (await _repos(db, org_id, [spec.repo_id]))[spec.repo_id]
    await record_event(
        db,
        org_id,
        bud_id,
        _RELEASE_EVENT[spec.stage],
        detail={
            "release_pr_number": spec.pr_number,
            "repo_name": repo.name,
            "release_pr_html_url": f"https://github.invalid/{repo.github_repo_full_name}/pull/{spec.pr_number}",
            "release_pr_title": spec.title,
            "release_pr_author": "e2e-release",
            "merged_at": datetime.now(UTC).isoformat(),
            "matched_commits": [],
        },
    )
    await db.commit()
