"""BUD pull request endpoints — PR list and merge checklist."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.pull_request import PullRequestRepository
from app.schemas.pull_request import PRChecklistItem, PullRequestRead

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
        pr = pr_by_repo.get(repo_id)
        if pr and pr.state == "merged":
            item_status = "merged"
        elif pr:
            item_status = "open"
        else:
            item_status = "no_pr"
        items.append(PRChecklistItem(
            repo_id=repo_id,
            repo_name=repo_name,
            pr=pr,
            status=item_status,
        ))

    return items
