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

"""Consolidate split GitHub/work-email identities onto one member per person.

Engineers accumulated two or three ``users`` rows: a work-email member
holding the role, memberships and BUD assignments, and one or more
GitHub stubs (``{login}@users.noreply.github.com`` or the numeric
``{id}+{login}@…`` form) holding every pull request. Per-person
throughput and capacity views therefore read zero for the real member.

The script pairs stubs to real members, then for each pair performs the
same transfer the Settings → Members → Merge flow now does:

* re-point ``pull_requests.author_user_id`` onto the target
* fold reward events, XP/SP totals and skill profiles onto the target
* rebind the stub's emails as aliases on the target
* move ``github_username`` to the target and clear it on the stub
* deactivate the stub

Run with ``--dry-run`` first: it prints the full pairing table and
changes nothing. Nothing is written until ``--apply`` is passed.

Pairing is deliberately conservative. Only *active* members are eligible
targets — a deactivated row is usually the losing side of an earlier
merge, and folding fresh history onto it would re-bury the attribution
this script exists to recover. A stub matches only when it maps to
exactly one candidate by, in order: an alias on its own address; an
alias on a sibling stub sharing its GitHub login; the work-email local
part; or a unique display-name match. Ambiguous or unmatched stubs are
reported and skipped for a human to resolve — the script never guesses.

Where a login resembles neither the work email nor the display name,
pair it explicitly with ``--map LOGIN=EMAIL`` rather than loosening the
rules for everyone. An override naming a login with no matching stub is
a hard error, so a typo fails loudly instead of silently skipping.

Usage::

    python -m scripts.backfill_github_identities --org-slug acme --dry-run
    python -m scripts.backfill_github_identities --org-slug acme \\
        --map someone01=someone@acme.com --apply
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.organization import Organization
from app.models.pull_request import PullRequest
from app.models.user import OrgToUser, User, UserEmailAlias
from app.repositories.developer_xp import DeveloperXPRepository, RewardEventRepository
from app.repositories.pull_request import PullRequestRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.user import UserRepository

logger = structlog.get_logger(__name__)

# Matches both GitHub noreply forms: "login@users.noreply.github.com" and
# the numeric "12345+login@users.noreply.github.com".
NOREPLY_RE = re.compile(
    r"^(?:(?P<gh_id>\d+)\+)?(?P<login>[^@+]+)@users\.noreply\.github\.com$",
    re.IGNORECASE,
)


@dataclass
class Candidate:
    """One stub → real-member pairing decision."""

    stub_id: uuid.UUID
    stub_email: str
    stub_login: str | None
    pr_count: int
    target_id: uuid.UUID | None = None
    target_email: str | None = None
    reason: str = ""
    conflicts: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        """True when this stub has exactly one confident target."""
        return self.target_id is not None


def _login_of(email: str) -> str | None:
    """Extract the GitHub login from a noreply address, if it is one."""
    match = NOREPLY_RE.match(email.strip())
    return match.group("login").lower() if match else None


async def _load_org(db: AsyncSession, slug: str) -> Organization:
    """Fetch the organization by slug, or exit with a clear message."""
    org = (
        await db.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()
    if org is None:
        sys.exit(f"No organization with slug {slug!r}.")
    return org


async def _members(db: AsyncSession, org_id: uuid.UUID) -> list[User]:
    """Every user row belonging to the org."""
    stmt = (
        select(User)
        .join(OrgToUser, OrgToUser.user_id == User.id)
        .where(OrgToUser.org_id == org_id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def _pr_counts(db: AsyncSession, org_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """PR count per author within the org."""
    stmt = (
        select(PullRequest.author_user_id, func.count().label("n"))
        .where(PullRequest.org_id == org_id, PullRequest.author_user_id.is_not(None))
        .group_by(PullRequest.author_user_id)
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


async def _alias_owners(db: AsyncSession, org_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Map every existing alias email to its owning user."""
    stmt = select(UserEmailAlias.email, UserEmailAlias.user_id).where(
        UserEmailAlias.org_id == org_id
    )
    return {row[0].lower(): row[1] for row in (await db.execute(stmt)).all()}


def _pair(
    stubs: list[User],
    reals: list[User],
    pr_counts: dict[uuid.UUID, int],
    aliases: dict[str, uuid.UUID],
    overrides: dict[str, str],
) -> list[Candidate]:
    """Pair each stub to at most one real member, conservatively.

    Only *active* members are eligible targets. A deactivated row is
    usually the losing side of an earlier merge, and folding fresh PR
    history onto it would re-bury the very attribution this script
    exists to recover.

    Rules run in descending order of evidence strength:

    0. an operator-supplied ``--map login=email`` override — the only
       way to pair a login that shares nothing with the member's work
       email or display name, and deliberately a conscious human call;
    1. an alias on this stub's own address;
    2. an alias on a *sibling* stub carrying the same GitHub login —
       GitHub issues both ``login@`` and ``{id}+login@`` forms for one
       person, so a decision already recorded for one form is binding
       for the other;
    3. the GitHub login equals the work-email local part;
    4. exactly one active member shares the stub's display name.

    Anything else is reported and skipped rather than guessed.
    """
    active = [u for u in reals if u.is_active]
    by_email = {u.email.lower(): u for u in active}
    by_id = {u.id: u for u in active}
    by_local = {u.email.split("@", 1)[0].lower(): u for u in active}
    by_name: dict[str, list[User]] = {}
    for user in active:
        by_name.setdefault(user.name.strip().lower(), []).append(user)

    # Login → target implied by an alias already recorded on any stub form.
    by_sibling_login: dict[str, User] = {}
    for alias_email, owner_id in aliases.items():
        alias_login = _login_of(alias_email)
        owner = by_id.get(owner_id)
        if alias_login and owner is not None:
            by_sibling_login.setdefault(alias_login, owner)

    candidates: list[Candidate] = []
    for stub in stubs:
        login = stub.github_username or _login_of(stub.email)
        key = (login or "").lower()
        cand = Candidate(
            stub_id=stub.id,
            stub_email=stub.email,
            stub_login=login,
            pr_count=pr_counts.get(stub.id, 0),
        )

        forced = by_email.get(overrides.get(key, "")) if key else None
        direct = by_id.get(aliases.get(stub.email.lower(), uuid.uuid4()))
        sibling = by_sibling_login.get(key) if key else None
        local = by_local.get(key) if key else None
        same_name = by_name.get(stub.name.strip().lower(), [])

        if forced is not None:
            match, reason = forced, "operator override"
        elif direct is not None:
            match, reason = direct, "existing alias"
        elif sibling is not None:
            match, reason = sibling, "sibling-login alias"
        elif local is not None:
            match, reason = local, "email local-part"
        elif len(same_name) == 1:
            match, reason = same_name[0], "exact name"
        else:
            cand.reason = "ambiguous name" if len(same_name) > 1 else "no match"
            cand.conflicts = [u.email for u in same_name]
            candidates.append(cand)
            continue

        cand.target_id, cand.target_email, cand.reason = match.id, match.email, reason
        candidates.append(cand)

    return candidates


def _report(candidates: list[Candidate]) -> None:
    """Print the pairing table and a summary."""
    resolved = [c for c in candidates if c.resolved]
    skipped = [c for c in candidates if not c.resolved]

    print(f"\n{'STUB':<52} {'PRs':>5}  {'→ TARGET':<40} REASON")
    print("-" * 122)
    for cand in sorted(resolved, key=lambda c: -c.pr_count):
        print(
            f"{cand.stub_email:<52} {cand.pr_count:>5}  "
            f"{cand.target_email or '':<40} {cand.reason}"
        )

    if skipped:
        print(f"\nSKIPPED — needs a human decision ({len(skipped)}):")
        for cand in sorted(skipped, key=lambda c: -c.pr_count):
            extra = f" [{', '.join(cand.conflicts)}]" if cand.conflicts else ""
            print(f"  {cand.stub_email:<52} {cand.pr_count:>5} PRs  {cand.reason}{extra}")

    print(
        f"\n{len(resolved)} stub(s) pairable, moving "
        f"{sum(c.pr_count for c in resolved)} pull request(s). "
        f"{len(skipped)} skipped."
    )


async def _apply(db: AsyncSession, org_id: uuid.UUID, candidates: list[Candidate]) -> None:
    """Perform the transfer for every resolved candidate."""
    user_repo = UserRepository(db, org_id=org_id)
    pr_repo = PullRequestRepository(db, org_id=org_id)
    sp_repo = SkillProfileRepository(db, org_id=org_id)
    xp_repo = DeveloperXPRepository(db, org_id=org_id)
    event_repo = RewardEventRepository(db, org_id=org_id)

    for cand in candidates:
        if not cand.resolved or cand.target_id is None:
            continue
        stub = await db.get(User, cand.stub_id)
        target = await db.get(User, cand.target_id)
        if stub is None or target is None:
            continue

        moved_prs = await pr_repo.repoint_author(stub.id, target.id)
        await sp_repo.transfer_profiles(stub.id, target.id)
        await xp_repo.merge_into_target(stub.id, target.id)
        await event_repo.repoint_user(stub.id, target.id)

        stub_aliases = await user_repo.list_aliases(stub.id)
        await user_repo.rebind_aliases_to_target(
            org_id, target.id, {stub.email} | {a.email for a in stub_aliases}
        )

        login = stub.github_username or cand.stub_login
        if login and not target.github_username:
            target.github_username = login
        stub.github_username = None
        stub.is_active = False
        await db.flush()

        logger.info(
            "identity_backfilled",
            stub=stub.email,
            target=target.email,
            github_username=login,
            pull_requests_repointed=moved_prs,
        )


async def main() -> None:
    """Entry point: pair stubs to members, report, and optionally apply."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-slug", required=True, help="Organization slug to process.")
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="LOGIN=EMAIL",
        dest="overrides",
        help=(
            "Force a GitHub login onto a member's work email, for people whose "
            "login resembles neither their email nor their display name. "
            "Repeatable."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")
    mode.add_argument("--apply", action="store_true", help="Perform the transfer.")
    args = parser.parse_args()

    overrides: dict[str, str] = {}
    for pair in args.overrides:
        login, sep, email = pair.partition("=")
        if not sep or not login.strip() or not email.strip():
            sys.exit(f"--map expects LOGIN=EMAIL, got {pair!r}.")
        overrides[login.strip().lower()] = email.strip().lower()

    async with AsyncSessionLocal() as db:
        org = await _load_org(db, args.org_slug)
        members = await _members(db, org.id)
        pr_counts = await _pr_counts(db, org.id)
        aliases = await _alias_owners(db, org.id)

        stubs = [u for u in members if _login_of(u.email) is not None]
        reals = [u for u in members if _login_of(u.email) is None]
        candidates = _pair(stubs, reals, pr_counts, aliases, overrides)

        unknown = overrides.keys() - {(c.stub_login or "").lower() for c in candidates}
        if unknown:
            sys.exit(f"--map login(s) not present as a GitHub stub: {', '.join(sorted(unknown))}")

        print(f"Org: {org.name} ({org.slug})")
        print(f"{len(members)} member rows — {len(stubs)} GitHub stub(s), {len(reals)} real.")
        _report(candidates)

        if args.dry_run:
            print("\nDry run — nothing written.")
            return

        await _apply(db, org.id, candidates)
        await db.commit()
        print("\nApplied.")


if __name__ == "__main__":
    asyncio.run(main())
