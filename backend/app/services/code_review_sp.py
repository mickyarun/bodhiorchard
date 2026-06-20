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

"""Award Skill Points to people who gave a valid code review on a BUD.

Reviewers arrive as GitHub logins in ``bud.code_review_comments``. Each is
mapped to a canonical internal user (alias / merge aware, so a blank
``github_username`` no longer drops the award), checked against the judge's
per-reviewer validity verdict (rubber-stamp "LGTM" → no SP), and excluded
if they also authored work on the BUD (no self-review credit). The amount
is role-based: developers and tech leads earn review SP, other roles don't.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.services.identity_resolution import resolve_canonical_user
from app.services.sp_rules import REVIEW_SP
from app.services.sp_service import award_sp, get_user_role

logger = structlog.get_logger(__name__)


def _distinct_reviewer_logins(bud: BUDDocument) -> set[str]:
    """GitHub logins that left a non-empty review comment on the BUD."""
    logins: set[str] = set()
    for entry in bud.code_review_comments or []:
        if not isinstance(entry, dict):
            continue
        author = entry.get("author")
        body = (entry.get("body") or "").strip()
        if author and body:
            logins.add(author)
    return logins


async def award_code_review_sp(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    review_validity: dict[str, bool],
    *,
    exclude_user_ids: set[uuid.UUID],
) -> int:
    """Award review SP per valid, non-self reviewer. Returns count credited.

    ``review_validity`` is the judge verdict keyed by GitHub login; a login
    absent from it defaults to valid (the judge only ran for multi-reviewer
    BUDs). ``exclude_user_ids`` are the BUD's own contributors — a reviewer
    resolving to one of them is a self-review and earns nothing.
    """
    awarded = 0
    for login in _distinct_reviewer_logins(bud):
        if not review_validity.get(login, True):
            continue
        user_id = await resolve_canonical_user(db, org_id, github_login=login)
        if user_id is None or user_id in exclude_user_ids:
            continue
        role = await get_user_role(db, user_id, org_id)
        amount = REVIEW_SP.get(role)
        if not amount:
            continue
        result = await award_sp(
            db,
            user_id=user_id,
            org_id=org_id,
            amount=amount,
            source="sp_review",
            source_ref=f"sp_review:{bud.bud_number}:{user_id}",
        )
        if result is not None:
            awarded += 1
    return awarded
