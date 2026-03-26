"""Unauthenticated public endpoints for git hook integration.

These endpoints are called by pre-commit and post-commit hooks installed
in tracked repositories. No JWT auth required — rate limited instead.
Org-scoped via UUID path parameter (baked into hooks at install time).
"""

import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.bud import BUDDocument

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["public"])

# ── Simple in-memory rate limiter ──────────────────────────────────
_rate_store: dict[str, list[float]] = {}
_RATE_WINDOW = 60  # seconds
_RATE_LIMIT = 60  # requests per window per IP
_MAX_TRACKED_IPS = 10_000  # cap to prevent unbounded memory growth


def _check_rate_limit(client_ip: str) -> None:
    """Raise 429 if the client exceeds the rate limit."""
    now = time.monotonic()

    # Evict stale IPs if store grows too large
    if len(_rate_store) > _MAX_TRACKED_IPS:
        cutoff = now - _RATE_WINDOW
        stale = [ip for ip, ts in _rate_store.items() if not ts or ts[-1] < cutoff]
        for ip in stale:
            del _rate_store[ip]

    timestamps = _rate_store.get(client_ip, [])
    # Prune old entries for this IP
    timestamps = [t for t in timestamps if now - t < _RATE_WINDOW]
    if len(timestamps) >= _RATE_LIMIT:
        _rate_store[client_ip] = timestamps
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limited")
    timestamps.append(now)
    _rate_store[client_ip] = timestamps


# ── BUD Check (pre-commit hook) ───────────────────────────────────


@router.get("/{org_id}/bud-check/{bud_number}")
async def check_bud_exists(
    org_id: uuid.UUID,
    bud_number: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Check if a BUD exists by number within an organization.

    Called by pre-commit hooks to validate branch naming.
    Org-scoped via path parameter (baked into hook at install time).
    No authentication required.
    """
    _check_rate_limit(request.client.host if request.client else "unknown")

    result = await db.execute(
        select(BUDDocument.id)
        .where(BUDDocument.bud_number == bud_number, BUDDocument.org_id == org_id)
        .limit(1)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BUD-{bud_number} not found",
        )
    return {"exists": True}


# ── BUD Commit (post-commit hook) ─────────────────────────────────


class BUDCommitRequest(BaseModel):
    """Schema for reporting a commit from a post-commit hook."""

    bud_number: int
    sha: str = Field(..., min_length=7, max_length=40)
    message: str = Field(..., max_length=500)
    files: str = Field(default="", max_length=5000)
    repo_path: str = Field(..., max_length=1000)
    branch: str = Field(..., max_length=500)
    author: str = Field(default="", max_length=255)
    author_email: str = Field(default="", max_length=255)


@router.post("/{org_id}/bud-commit", status_code=status.HTTP_201_CREATED)
async def record_bud_commit(
    org_id: uuid.UUID,
    body: BUDCommitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Record a commit associated with a BUD within an organization.

    Called by post-commit hooks. Fire-and-forget from the hook's perspective.
    Deduplicates by commit SHA. Org-scoped via path parameter.
    No authentication required.
    """
    _check_rate_limit(request.client.host if request.client else "unknown")

    from app.repositories.bud_commit import BUDCommitRepository

    # Find the BUD by number scoped to the org
    result = await db.execute(
        select(BUDDocument)
        .where(BUDDocument.bud_number == body.bud_number, BUDDocument.org_id == org_id)
        .limit(1)
    )
    bud = result.scalar_one_or_none()
    if bud is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BUD-{body.bud_number} not found",
        )

    # Resolve commit author to a Bodhigrove user (check email + aliases)
    resolved_user_id: uuid.UUID | None = None
    if body.author_email:
        from app.models.user import UserEmailAlias
        from app.repositories.user import UserRepository

        user_repo = UserRepository(db)
        user = await user_repo.get_by_email_in_org(org_id, body.author_email)
        if not user:
            alias_result = await db.execute(
                select(UserEmailAlias).where(
                    UserEmailAlias.org_id == org_id,
                    UserEmailAlias.email == body.author_email,
                )
            )
            alias = alias_result.scalar_one_or_none()
            if alias:
                from app.models.user import User

                user = await db.get(User, alias.user_id)
        if user:
            resolved_user_id = user.id

    commit_repo = BUDCommitRepository(db, org_id=org_id)
    commit = await commit_repo.create_commit(
        bud_id=bud.id,
        repo_path=body.repo_path,
        branch_name=body.branch,
        commit_sha=body.sha,
        commit_message=body.message,
        files_changed=body.files,
        author_name=body.author or None,
        author_email=body.author_email or None,
        user_id=resolved_user_id,
    )

    if commit is None:
        return {"status": "duplicate"}

    logger.info(
        "bud_commit_recorded",
        bud_number=body.bud_number,
        sha=body.sha[:8],
        author=body.author,
        repo_path=body.repo_path,
    )
    return {"status": "created"}
