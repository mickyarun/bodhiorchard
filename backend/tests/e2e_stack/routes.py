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

"""``/__e2e`` routes: seed data for one browser test, reset, and the guard log.

Only :mod:`tests.e2e_stack.serve` mounts this router, on a server bound to
loopback and backed by a throwaway database.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.permission_seeder import seed_permissions
from tests.e2e_stack.seed_org import seed_org
from tests.e2e_stack.specs import GuardReport, Identity, OrgSpec, SeededOrg
from tests.e2e_stack.state import STATE

router = APIRouter(prefix="/__e2e", tags=["e2e"])

_KEEP_TABLES = ("alembic_version",)
_REPO_ROOT = Path(__file__).resolve().parents[3]


@router.post("/orgs", response_model=SeededOrg, response_model_by_alias=True)
async def create_org(spec: OrgSpec) -> SeededOrg:
    """Seed an org (or extend the oldest one) with members and leave types."""
    async with AsyncSessionLocal() as db:
        return await seed_org(db, spec)


@router.post("/reset", status_code=204, response_class=Response)
async def reset() -> Response:
    """Empty every table, then re-seed permissions, so the setup wizard shows.

    Only the setup wizard spec calls this, and Playwright runs it before any
    other spec starts.
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
async def guard_report() -> GuardReport:
    """Every external call the fakes refused, and any agent run they had to fail."""
    guard, claude = STATE.guard, STATE.claude
    problems = list(claude.problems) if claude else []
    if claude:
        problems += [f"unscripted agent run: {run.prompt[:120]!r}" for run in claude.unscripted]
    return GuardReport(
        violations=list(guard.violations) if guard else [],
        agent_problems=problems,
        agent_runs=len(claude.runs) if claude else 0,
    )


@router.get("/identity", response_model=Identity, response_model_by_alias=True)
async def identity() -> Identity:
    """The checkout this server was started from."""
    return Identity(repo_root=str(_REPO_ROOT))
