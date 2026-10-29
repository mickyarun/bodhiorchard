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

"""``/__e2e`` routes about the stack itself: reset, guard report, identity.

Only :mod:`tests.e2e_stack.serve` mounts these, on a server bound to
loopback and backed by a throwaway database.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query, Response
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.permission_seeder import seed_permissions
from tests.e2e_stack.specs import GuardReport, Identity
from tests.e2e_stack.state import STATE

router = APIRouter(prefix="/__e2e", tags=["e2e"])

_KEEP_TABLES = ("alembic_version",)
_REPO_ROOT = Path(__file__).resolve().parents[3]


@router.post("/reset", status_code=204, response_class=Response)
async def reset() -> Response:
    """Empty every table, then re-seed permissions, so the setup wizard shows.

    Only the setup wizard spec calls this, on the wizard's own backend.
    """
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = sorted(set(rows.scalars()) - set(_KEEP_TABLES))
        quoted = ", ".join(f'"{name}"' for name in tables)
        await db.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
        await seed_permissions(db)
        await db.commit()
    return Response(status_code=204)


@router.get("/guard", response_model=GuardReport, response_model_by_alias=True)
async def guard_report(
    test: str | None = Query(None), every: bool = Query(False, alias="all")
) -> GuardReport:
    """What the fakes refused while serving ``test``.

    No ``test``: what happened outside any test (job workers, scheduler
    loops). ``all``: everything, tagged with its test, for the end-of-run
    check that also catches what a test caused after its own check ran.
    """
    if every:
        return GuardReport(
            violations=STATE.refusals.everything(),
            agent_problems=STATE.agent_problems.everything(),
        )
    return GuardReport(
        violations=STATE.refusals.for_test(test),
        agent_problems=STATE.agent_problems.for_test(test),
    )


@router.get("/identity", response_model=Identity, response_model_by_alias=True)
async def identity() -> Identity:
    """The checkout this server was started from."""
    return Identity(repo_root=str(_REPO_ROOT))
