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

"""Fold deactivated / external contributor rows into their merge target.

The contributor breakdown persisted at BUD close is a snapshot of who
held an account when the Learning Agent ran. When Settings → Members
later merges user B into user A, B's primary email becomes a
``UserEmailAlias`` on A and B is deactivated — but the persisted
contributor row still names B (or shows the PR as an "(external)"
github_login row when B never had a user_id at PR-ingest time).

This module is invoked at read time by the GET /buds/{id}/learning
endpoint to re-attribute those rows to the currently-active merge
target via the alias backlink, without rewriting the stored JSONB.
The stored snapshot stays untouched so a later un-merge or alias
change is reflected on the next fetch.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.user_resolution import walk_to_active_user


async def resolve_aliased_contributors(
    db: AsyncSession,
    org_id: uuid.UUID,
    contributors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return ``contributors`` with merge-target rows folded together."""
    if not contributors:
        return contributors
    user_repo = UserRepository(db)

    by_uid: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []

    for row in contributors:
        target = await _resolve_active_target(db, user_repo, org_id, row)
        if target is None:
            pending.append(dict(row))
            continue
        key = str(target.id)
        existing = by_uid.get(key)
        counts = _row_counts(row)
        if existing is None:
            by_uid[key] = {
                "user_id": key,
                "github_login": None,
                "name": target.name or target.email,
                **counts,
            }
        else:
            existing["commits"] += counts["commits"]
            existing["prs_merged"] += counts["prs_merged"]
            existing["todos_completed"] += counts["todos_completed"]
            existing["active_days"] = max(existing["active_days"], counts["active_days"])

    merged = list(by_uid.values()) + pending
    merged.sort(
        key=lambda r: (r.get("commits", 0), r.get("prs_merged", 0)),
        reverse=True,
    )
    return merged


async def _resolve_active_target(
    db: AsyncSession,
    user_repo: UserRepository,
    org_id: uuid.UUID,
    row: dict[str, Any],
) -> User | None:
    """Return the currently-active User for a contributor row, if any.

    Resolution order: explicit user_id (active → return; deactivated →
    walk merge backlink), then github_login (resolve via username,
    walk backlink if deactivated). Returns None when nothing resolves
    to an active user — the caller then preserves the row verbatim so
    truly-external collaborators stay visible.
    """
    uid_str = row.get("user_id")
    if uid_str:
        try:
            user = await db.get(User, uuid.UUID(str(uid_str)))
        except ValueError:
            user = None
        return await walk_to_active_user(db, org_id, user)

    login = row.get("github_login")
    if not login:
        return None
    resolved_uid = await user_repo.get_id_by_github_login(org_id, login)
    if resolved_uid is None:
        return None
    user = await db.get(User, resolved_uid)
    return await walk_to_active_user(db, org_id, user)


def _row_counts(row: dict[str, Any]) -> dict[str, int]:
    """Coerce the four count fields to ints with a 0 default."""
    return {
        "commits": int(row.get("commits") or 0),
        "prs_merged": int(row.get("prs_merged") or 0),
        "todos_completed": int(row.get("todos_completed") or 0),
        "active_days": int(row.get("active_days") or 0),
    }
