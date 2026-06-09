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

"""Repo-team filter for the BUD auto-assignment candidate pool.

The role-based picker in ``bud_assignment._resolve_via_chain`` calls
this helper to intersect its role-eligible users with the membership
of any team that owns one of the BUD's impacted repos. That keeps
work routed to the squad that actually owns the code, not just any
person in the org with the right title.

Three outcomes the caller needs to distinguish:

1. **No impacted repos on the BUD** (typical before the tech-arch
   stage runs, or every entry in the JSONB list was malformed) —
   filter is skipped and the original pool is returned. The
   ``applied`` flag stays ``False`` because nothing was attempted.
   When the input WAS non-empty but every entry parsed badly,
   ``input_malformed=True`` so observers can tell "no repos" apart
   from "all repos corrupt".

2. **Impacted repos present, filter narrowed the pool** — narrowed
   pool returned; ``fell_back=False``.

3. **Impacted repos present but no owning team has a member in this
   role pool** — original (org-wide) pool returned; ``fell_back=True``
   so the banner can say "no team owns <repo>, or no <role> in an
   owning team — assigned org-wide". Falling back rather than
   starving the BUD matches the "stage flow never stalls silently"
   principle the assignment service already applies to missing roles.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.team import TeamRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TeamScopeResult:
    """Outcome of applying repo-team filtering to a candidate pool.

    Field semantics:

    - ``candidates``: the pool to hand back to the caller. Equal to
      the input pool when ``applied=False`` OR ``fell_back=True``;
      strictly narrower than the input when ``applied=True`` and
      ``fell_back=False``.
    - ``applied``: whether we attempted to narrow the pool. ``False``
      means there were no usable impacted-repo IDs to filter against.
    - ``fell_back``: filter ran but produced no candidates, so we
      handed back the unfiltered pool. The lifecycle event surfaces
      this so the banner can warn the admin.
    - ``impacted_repo_count``: count of *valid* repo IDs we filtered
      on. Together with ``raw_repo_entries`` and ``discarded_count``
      it tells observers how much of the BUD's declared impact we
      actually scoped against.
    - ``raw_repo_entries`` / ``discarded_count``: corruption visibility
      so a single survivor doesn't masquerade as the whole impact set.
    - ``input_malformed``: True when the input list was non-empty but
      every entry failed parsing (the single most misleading case for
      a confident "scoped" banner).
    - ``team_pool_size``: union of team members across all owning
      teams BEFORE intersecting with the role pool. Helps distinguish
      "no team owns this repo at all" (size 0) from "team owns the
      repo but no member is in the eligible role pool" (size > 0).
    """

    candidates: list[User]
    applied: bool
    fell_back: bool
    impacted_repo_count: int
    team_pool_size: int
    raw_repo_entries: int = 0
    discarded_count: int = 0
    input_malformed: bool = False


def _extract_repo_ids(impacted_repos: Sequence[Any] | None) -> tuple[list[uuid.UUID], int]:
    """Pull deduped UUID repo_ids out of the BUD's JSONB ``impacted_repos``.

    Returns ``(ids, discarded_count)`` so the caller can surface the
    discard count rather than silently treating survivors as the
    authoritative impact set. Every skipped entry logs at WARNING
    level (config drift / stale BUD JSONB is exactly what an admin
    needs visibility on); a summary line fires when ``discarded_count > 0``.
    """
    if not impacted_repos:
        return [], 0
    seen: dict[uuid.UUID, None] = {}
    discarded = 0
    for entry in impacted_repos:
        if not isinstance(entry, dict):
            logger.warning("team_scope_repo_entry_not_dict", entry_type=type(entry).__name__)
            discarded += 1
            continue
        raw = entry.get("repo_id")
        if not isinstance(raw, str):
            logger.warning("team_scope_repo_id_missing_or_non_string", entry=entry)
            discarded += 1
            continue
        try:
            uid = uuid.UUID(raw)
        except ValueError:
            logger.warning("team_scope_bad_repo_id_uuid", raw=raw)
            discarded += 1
            continue
        if uid in seen:
            # Dedupe rather than counting as a discard — duplicate
            # entries are a tech-arch agent quirk, not corruption.
            continue
        seen[uid] = None
    if discarded > 0:
        logger.warning(
            "team_scope_repo_entries_discarded",
            kept=len(seen),
            discarded=discarded,
            total=len(impacted_repos),
        )
    return list(seen), discarded


async def filter_candidates_by_team_ownership(
    db: AsyncSession,
    org_id: uuid.UUID,
    candidates: list[User],
    impacted_repos: Sequence[Any] | None,
) -> TeamScopeResult:
    """Return a ``TeamScopeResult`` describing the filtered candidate pool.

    See the module docstring for the three outcomes; the caller
    (``_resolve_via_chain``) uses ``applied`` + ``fell_back`` to stamp
    the lifecycle banner so admins can see at a glance whether the
    pick was team-scoped, org-wide because no repos, or org-wide
    because no team owned them yet.

    The ``TeamRepository`` call is intentionally NOT wrapped in
    try/except: a DB failure on the team query is a real operational
    incident; silently degrading to a wider pool here would (a)
    produce assignments that contradict declared ownership, (b)
    stamp ``team_scope_applied=False`` so observers think the BUD
    had no impacted repos, and (c) hide a failing query from Sentry.
    Propagate, let the PATCH handler return 500, let the user retry.
    """
    raw_count = len(impacted_repos or [])
    repo_ids, discarded = _extract_repo_ids(impacted_repos)
    if not repo_ids:
        return TeamScopeResult(
            candidates=candidates,
            applied=False,
            fell_back=False,
            impacted_repo_count=0,
            team_pool_size=0,
            raw_repo_entries=raw_count,
            discarded_count=discarded,
            input_malformed=raw_count > 0,
        )

    # An empty role pool is the caller's responsibility — the
    # chain-walker already ``continue``s on that branch before calling
    # us. We assert here rather than handling a dead branch.
    assert candidates, "filter_candidates_by_team_ownership requires a non-empty pool"

    team_repo = TeamRepository(db, org_id=org_id)
    team_user_ids = await team_repo.list_member_ids_for_repos(repo_ids)

    if not team_user_ids:
        # No team has been mapped to any impacted repo yet.
        logger.warning(
            "team_scope_no_team_owner",
            org_id=str(org_id),
            repo_ids=[str(r) for r in repo_ids],
        )
        return TeamScopeResult(
            candidates=candidates,
            applied=True,
            fell_back=True,
            impacted_repo_count=len(repo_ids),
            team_pool_size=0,
            raw_repo_entries=raw_count,
            discarded_count=discarded,
        )

    filtered = [c for c in candidates if c.id in team_user_ids]
    if not filtered:
        # Team(s) own the repos but no member matches this role pool.
        logger.warning(
            "team_scope_no_role_match_in_team",
            org_id=str(org_id),
            repo_ids=[str(r) for r in repo_ids],
            role_pool_size=len(candidates),
            team_pool_size=len(team_user_ids),
        )
        return TeamScopeResult(
            candidates=candidates,
            applied=True,
            fell_back=True,
            impacted_repo_count=len(repo_ids),
            team_pool_size=len(team_user_ids),
            raw_repo_entries=raw_count,
            discarded_count=discarded,
        )

    return TeamScopeResult(
        candidates=filtered,
        applied=True,
        fell_back=False,
        impacted_repo_count=len(repo_ids),
        team_pool_size=len(team_user_ids),
        raw_repo_entries=raw_count,
        discarded_count=discarded,
    )


async def user_is_in_owning_team(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    impacted_repos: Sequence[Any] | None,
) -> bool:
    """True when ``user_id`` belongs to a team owning any impacted repo.

    Used by the continuity path so a previously-assigned user who has
    since been removed from every owning team falls out of continuity
    rather than silently bypassing team scope on phase re-entry. When
    ``impacted_repos`` is empty / all-malformed we treat the user as
    eligible — the BUD itself has no scope to validate against, so
    continuity behaviour matches the pre-scope behaviour.
    """
    repo_ids, _ = _extract_repo_ids(impacted_repos)
    if not repo_ids:
        return True
    team_repo = TeamRepository(db, org_id=org_id)
    team_user_ids = await team_repo.list_member_ids_for_repos(repo_ids)
    return user_id in team_user_ids
