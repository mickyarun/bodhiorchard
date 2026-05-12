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

"""BUD pull request endpoints — PR list, merge checklist, release stages."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.pull_request import PullRequestRepository
from app.schemas.bud_release import (
    BUDReleaseStage,
    ReleaseCommit,
    ReleasePR,
    ReleaseStage,
    ReleaseStageStatus,
    ReleaseTimelineEvent,
)
from app.schemas.pull_request import PRChecklistItem, PullRequestRead
from app.utils.branch_matching import branch_matches

router = APIRouter()


@router.get(
    "/{bud_id}/pull-requests",
    response_model=list[PullRequestRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_bud_pull_requests(
    bud_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PullRequestRead]:
    """List all PRs linked to a BUD with merge status."""
    pr_repo = PullRequestRepository(db, org_id=current_user.org_id)
    prs = await pr_repo.list_for_bud(bud_id)
    return [PullRequestRead.model_validate(pr) for pr in prs]


@router.get(
    "/{bud_id}/pr-checklist",
    response_model=list[PRChecklistItem],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_pr_checklist(
    bud_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PRChecklistItem]:
    """Get merge checklist: each impacted repo with its PR status."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if not bud:
        return []

    impacted = bud.impacted_repos or []
    if not impacted:
        return []

    pr_repo = PullRequestRepository(db, org_id=current_user.org_id)
    prs = await pr_repo.list_for_bud(bud_id)

    # Index PRs by repo_id (latest per repo)
    pr_by_repo: dict[str, PullRequestRead] = {}
    for pr in prs:
        if pr.repo_id:
            rid = str(pr.repo_id)
            if rid not in pr_by_repo:
                pr_by_repo[rid] = PullRequestRead.model_validate(pr)

    items: list[PRChecklistItem] = []
    for repo in impacted:
        repo_id = repo.get("repo_id", "")
        repo_name = repo.get("repo_name", "unknown")
        pr_view: PullRequestRead | None = pr_by_repo.get(repo_id)
        if pr_view and pr_view.state == "merged":
            item_status = "merged"
        elif pr_view:
            item_status = "open"
        else:
            item_status = "no_pr"
        items.append(
            PRChecklistItem(
                repo_id=repo_id,
                repo_name=repo_name,
                pr=pr_view,
                status=item_status,
            )
        )

    return items


@router.get(
    "/{bud_id}/release-stages/{stage}",
    response_model=BUDReleaseStage,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_bud_release_stage(
    bud_id: uuid.UUID,
    stage: Literal["uat", "prod"],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BUDReleaseStage:
    """Return release-stage detail (PRs, commits, events) for a BUD.

    Reads the ``merged_to_{stage}`` timeline events written by
    ``release_detection.detect_release_promotion`` and reshapes them into
    the ``BUDReleaseStage`` payload that drives the UAT and Prod tabs on
    the BUD detail page. Status is derived from event presence:

    - ``not_reached``: no events for this stage
    - ``in_stage``: events for this stage but not for the next one
    - ``passed``: only meaningful for ``uat`` \u2014 the BUD also has prod events
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if not bud:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BUD not found.",
        )

    typed_stage: ReleaseStage = stage
    target_event_type = f"merged_to_{typed_stage}"
    next_event_type = "merged_to_prod" if typed_stage == "uat" else None

    timeline_repo = BUDTimelineRepository(db, org_id=current_user.org_id)
    event_types = [target_event_type, next_event_type] if next_event_type else [target_event_type]
    all_events = await timeline_repo.list_for_bud_by_event_types(bud_id, event_types)

    stage_events = [e for e in all_events if e.event_type == target_event_type]
    next_events = [e for e in all_events if next_event_type and e.event_type == next_event_type]

    if not stage_events:
        derived_status: ReleaseStageStatus = "not_reached"
    elif next_events:
        derived_status = "passed"
    else:
        derived_status = "in_stage"

    release_prs: list[ReleasePR] = []
    commits: list[ReleaseCommit] = []
    timeline: list[ReleaseTimelineEvent] = []
    seen_pr_keys: set[tuple[int, str]] = set()
    first_reached = stage_events[0].created_at if stage_events else None

    for event in stage_events:
        d = event.detail or {}
        pr_number = d.get("release_pr_number")
        repo_name = d.get("repo_name", "")
        html_url = d.get("release_pr_html_url", "")
        if pr_number is not None:
            key = (int(pr_number), repo_name)
            if key not in seen_pr_keys:
                seen_pr_keys.add(key)
                release_prs.append(
                    ReleasePR(
                        pr_number=int(pr_number),
                        repo_name=repo_name,
                        html_url=html_url,
                        title=d.get("release_pr_title"),
                        author_login=d.get("release_pr_author"),
                        merged_at=_parse_iso(d.get("merged_at")),
                    ),
                )
            timeline.append(
                ReleaseTimelineEvent(
                    occurred_at=event.created_at,
                    pr_number=int(pr_number),
                    repo_name=repo_name,
                    html_url=html_url,
                ),
            )
        for c in d.get("matched_commits") or []:
            sha = (c.get("sha") or "") if isinstance(c, dict) else ""
            if not sha:
                continue
            commits.append(
                ReleaseCommit(
                    sha=sha,
                    short_sha=sha[:7],
                    message=c.get("message") if isinstance(c, dict) else None,
                    repo_name=repo_name,
                ),
            )

    # Open PRs targeting this stage's branch — gives visibility into
    # in-flight work before it merges and triggers release detection.
    #
    # Two sources:
    # 1. BUD-linked PRs (bud_id == this BUD) whose base_branch matches
    #    the stage target — covers direct bud-NNN/... → main PRs.
    # 2. Repo-scoped PRs (any bud_id or NULL) whose base_branch matches
    #    the stage target on an impacted repo — covers release PRs like
    #    develop → main that carry multiple BUDs and have no bud_id.
    open_prs: list[ReleasePR] = []
    seen_pr_ids: set[int] = set()

    impacted_repo_ids = [
        uuid.UUID(r.get("repo_id"))
        for r in (bud.impacted_repos or [])
        if isinstance(r, dict) and r.get("repo_id")
    ]

    pr_repo = PullRequestRepository(db, org_id=current_user.org_id)
    open_pr_pairs = await pr_repo.list_open_for_bud_with_repo(
        bud_id, impacted_repo_ids=impacted_repo_ids
    )
    for pr, repo in open_pr_pairs:
        if pr.github_pr_id in seen_pr_ids:
            continue
        target_branch = (
            (repo.uat_branch if typed_stage == "uat" else repo.main_branch) if repo else None
        )
        if target_branch and branch_matches(pr.base_branch, target_branch):
            seen_pr_ids.add(pr.github_pr_id)
            open_prs.append(
                ReleasePR(
                    pr_number=pr.github_pr_number,
                    repo_name=repo.name if repo else "",
                    html_url=pr.html_url,
                    title=pr.title,
                    author_login=pr.author_github_login,
                    merged_at=None,
                ),
            )

    return BUDReleaseStage(
        bud_id=str(bud_id),
        stage=typed_stage,
        status=derived_status,
        first_reached_at=first_reached,
        release_prs=release_prs,
        open_prs=open_prs,
        commits=commits,
        events=timeline,
    )


def _parse_iso(value: object) -> datetime | None:
    """Parse a stored ISO-8601 timestamp string back into a datetime.

    Detail JSON stores ``merged_at`` as a string (the raw GitHub field
    is preserved verbatim by ``record_event``). We rehydrate it here so
    the response schema's ``datetime`` field gets a real datetime, not a
    string. Returns ``None`` for missing or unparseable values rather
    than raising \u2014 the field is optional in the schema.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
