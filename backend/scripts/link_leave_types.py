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

"""Link an org's same-named leave types into the leave type library.

Usage (from backend/):
    python -m scripts.link_leave_types --org <slug> --actor <owner email>
        Dry run (the default): links everything inside a transaction, rolls
        it back and prints the report. Nothing changes.
    python -m scripts.link_leave_types --org <slug> --actor <email> --apply
        Links the groups that only differ in quota. Groups whose linking
        would change other fields are listed and skipped.
    ... --apply --accept "Earned leave" [--accept "Sick leave" ...]
        Also links the named groups, once the owner has read and confirmed
        their listed differences. The library entry keeps the first policy's
        values. --accept-all confirms every group at once.

Every linked type gets an event in its policy's history, by --actor.
"""

import argparse
import asyncio
import sys
from typing import Any

from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.leave.type_link_apply import (
    Acceptance,
    LinkOutcome,
    LinkStatus,
    link_existing_types,
)
from app.services.leave.type_link_plan import LinkGroup


def _value(value: Any) -> str:
    return "no limit" if value is None else str(value)


def _group_lines(group: LinkGroup) -> list[str]:
    source = "existing library entry" if group.existing else "new library entry"
    lines = [f"{group.name} ({group.rules['code']}), {source}, default quota "
             f"{_value(group.rules['annual_quota_days'])}"]  # fmt: skip
    for member in group.members:
        quota = f"own quota {_value(member.quota)}" if member.own_quota else "library quota"
        lines.append(f"  - {member.policy_name}: {member.type_name}, {quota}")
        for field, (current, library) in member.differences.items():
            lines.append(f"      {field}: {_value(current)} -> {_value(library)}")
    return lines


def _report(outcomes: list[LinkOutcome]) -> None:
    if not outcomes:
        print("Nothing to link: no names repeat across policies.")
    for outcome in outcomes:
        print("\n".join(_group_lines(outcome.group)))
        detail = f": {outcome.reason}" if outcome.reason else ""
        print(f"  => {outcome.status.value}{detail}\n")
    if any(o.group.needs_confirmation for o in outcomes):
        print("Fields listed under a policy change on that policy when it is linked.")
        print('Confirm them with the owner, then re-run with --apply --accept "<name>".')


async def _run(slug: str, actor_email: str, apply: bool, accepted: Acceptance) -> int:
    async with AsyncSessionLocal() as db:
        org = await OrganizationRepository(db).get_by_slug(slug)
        if org is None:
            print(f"No organisation with the slug {slug}.")
            return 2
        actor = await UserRepository(db).get_by_email_in_org(org.id, actor_email)
        if actor is None:
            print(f"{actor_email} isn't a member of {org.name}.")
            return 2
        org_name = org.name
        outcomes = await link_existing_types(db, org.id, actor.id, apply=apply, accepted=accepted)
    print(f"{'Applied' if apply else 'Dry run'} for {org_name}\n")
    _report(outcomes)
    return 1 if any(o.status == LinkStatus.BLOCKED for o in outcomes) else 0


def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--org", required=True, help="the organisation's slug")
    parser.add_argument("--actor", required=True, help="email recorded on the history events")
    parser.add_argument("--apply", action="store_true", help="keep the changes")
    parser.add_argument(
        "--accept",
        action="append",
        default=[],
        metavar="NAME",
        help="link this group although more than its quota changes (repeatable)",
    )
    parser.add_argument("--accept-all", action="store_true", help="accept every group's changes")
    args = parser.parse_args()
    accepted = Acceptance(names=frozenset(args.accept), everything=args.accept_all)
    sys.exit(asyncio.run(_run(args.org, args.actor, args.apply, accepted)))


if __name__ == "__main__":
    main()
