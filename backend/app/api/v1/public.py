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

"""Unauthenticated public endpoints for git hook integration.

Only the pre-commit BUD check endpoint remains here. Commit tracking
has moved to the authenticated POST /mcp/dev-activity endpoint.
"""

import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.bud import BUDRepository

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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limited",
        )
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
    _check_rate_limit(
        request.client.host if request.client else "unknown",
    )

    bud_repo = BUDRepository(db, org_id=org_id)
    if not await bud_repo.exists_by_number(bud_number):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BUD-{bud_number} not found",
        )
    return {"exists": True}
