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

"""Re-run the skill-extraction stage on every (or one) tracked repo for an org.

Usage:
    cd backend && python -m scripts.rerun_skills_for_org <org_id> \\
        [--repo <repo_id>] [--wipe --yes] [--dry-run]

When ``--wipe`` is set, every ``skill_profiles`` row for the org is
deleted before walking the repos. This is the one-off recovery path for
admins who have just fixed a bad email alias via Settings → Members and
need to clear orphaned attribution under deactivated users. Because the
delete is irreversible and org-wide, ``--wipe`` requires ``--yes`` so a
mistyped org id can't trash data.

``--dry-run`` reports the repos that would be walked (with resolved
branches) and the rows that ``--wipe`` would delete, then exits without
mutating anything.

Pause scans for the org before running. The script has no advisory lock
against a concurrent scan-pipeline ``skill_extraction`` stage; both
writers racing the same ``skill_profiles`` upserts (and the
``auto_create_members`` insert path) can interleave in ways the
``(user_id, org_id, module)`` constraint won't catch cleanly.

The script reuses the exact code path the scan pipeline runs
(``analyze_repo_skills`` → ``phase_e_skills``) so its output matches
what a future ``full_rescan=true`` scan would produce — just without
the cost of feature synthesis, design extraction, code indexing, or
embedding generation, none of which the email-alias fix affects.

Branch resolution follows the same precedence as the production stage:
``tracked_repositories.develop_branch`` (Gitflow), falling back to
``main_branch`` and finally HEAD if neither is configured.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.services.git_analyzer import analyze_repo_skills
from app.services.scan.phase_impls.skill_extraction import phase_e_skills
from app.services.scan_helpers import load_feature_map


def banner(text: str) -> None:
    """Print a section banner so the output reads cleanly."""
    print(f"\n{'=' * 70}\n  {text}\n{'=' * 70}")


def kv(label: str, value: object) -> None:
    """Two-column key/value line."""
    print(f"  {label:<38} {value}")


async def _run(
    org_id: uuid.UUID,
    repo_id: uuid.UUID | None,
    wipe: bool,
    dry_run: bool,
) -> int:
    async with AsyncSessionLocal() as db:
        org = await OrganizationRepository(db).get_by_id(org_id)
        if org is None:
            print(f"error: organization {org_id} not found", file=sys.stderr)
            return 2

        banner(f"Rerun skills for org {org.name} ({org_id})")
        kv("Mode", "dry-run (no writes)" if dry_run else "live")
        kv("Wipe before recompute", wipe)
        kv("Restricted to repo", repo_id or "(all active repos)")

        repo_repo = TrackedRepoRepository(db, org_id=org_id)
        repos = (
            ([r] if (r := await repo_repo.get_by_id(repo_id)) else [])
            if repo_id
            else await repo_repo.list_active()
        )
        if repo_id and not repos:
            print(f"error: tracked repo {repo_id} not found in org", file=sys.stderr)
            return 2

        sp_repo = SkillProfileRepository(db, org_id=org_id)
        if dry_run:
            existing = await sp_repo.count_profiles()
            kv("Existing profiles in org", existing)
            kv("Profiles --wipe would delete", existing if wipe else 0)
            banner(f"Would walk {len(repos)} repo(s)")
            for repo in repos:
                resolved_branch = repo.develop_branch or repo.main_branch or "(HEAD)"
                print(f"  {repo.name:<40} branch={resolved_branch}  path={repo.path}")
            print("\ndry-run complete; nothing was written.")
            return 0

        if wipe:
            deleted = await sp_repo.delete_all_for_org()
            kv("Profiles deleted", deleted)
            await db.commit()

        # The map is alias-aware (UserEmailAlias rows resolve to the
        # canonical member). Loaded once, mutated in place by phase_e_skills
        # as new members get auto-created — must NOT be rebound below.
        email_to_user = await UserRepository(db).get_email_map(org_id)

        banner(f"Walking {len(repos)} repo(s)")
        total_profiles = 0
        total_unmatched = 0
        for repo in repos:
            branch = repo.develop_branch or repo.main_branch
            feature_map = await load_feature_map(db, org_id, repo.id)
            entries = await analyze_repo_skills(repo.path, branch=branch, feature_map=feature_map)
            count, unmatched = await phase_e_skills(
                db=db,
                org_id=org_id,
                repo_path=repo.path,
                skill_entries=entries,
                email_to_user=email_to_user,
                scan_cfg={"auto_create_members": True},
            )
            await db.commit()
            total_profiles += count
            total_unmatched += len(unmatched)
            print(f"  {repo.name:<40} {count:>5} profiles  {len(unmatched):>3} unmatched")

        banner("Done")
        kv("Total profiles upserted", total_profiles)
        kv("Total unmatched emails", total_unmatched)
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rerun_skills_for_org",
        description=(
            "Wipe and/or recompute skill_profiles for one organization. "
            "Reuses the production skill-extraction stage without "
            "re-running indexing, synthesis, or embeddings."
        ),
    )
    parser.add_argument("org_id", type=uuid.UUID, help="Organization UUID")
    parser.add_argument(
        "--repo",
        type=uuid.UUID,
        default=None,
        help="Limit to a single tracked_repository UUID (defaults to all active repos)",
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Delete every existing skill_profile for the org before recomputing",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation when --wipe is set; refuses to run otherwise.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without writing anything.",
    )
    args = parser.parse_args()
    if args.wipe and not args.dry_run and not args.yes:
        parser.error("--wipe is destructive; pass --yes to confirm (or --dry-run to preview).")
    sys.exit(asyncio.run(_run(args.org_id, args.repo, args.wipe, args.dry_run)))


if __name__ == "__main__":
    main()
