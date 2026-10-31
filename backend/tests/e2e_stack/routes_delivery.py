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

"""``/__e2e`` routes for a BUD's delivery: repos, PRs, manual QA cases, releases.

Only :mod:`tests.e2e_stack.serve` mounts these, on a server bound to
loopback and backed by a throwaway database.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from app.database import AsyncSessionLocal
from tests.e2e_stack.seed_delivery import add_repo, record_release, set_delivery, set_manual_cases
from tests.e2e_stack.specs_delivery import (
    DeliverySpec,
    ManualCasesSpec,
    ReleaseSpec,
    RepoSpec,
    SeededRepo,
)

router = APIRouter(prefix="/__e2e/orgs/{org_id}", tags=["e2e"])


@router.post("/repos", response_model=SeededRepo, response_model_by_alias=True)
async def create_repo(org_id: uuid.UUID, spec: RepoSpec) -> SeededRepo:
    """Track a repository for the org."""
    async with AsyncSessionLocal() as db:
        return await add_repo(db, org_id, spec)


@router.post("/buds/{bud_id}/delivery", status_code=204, response_class=Response)
async def create_delivery(org_id: uuid.UUID, bud_id: uuid.UUID, spec: DeliverySpec) -> Response:
    """Set the BUD's impacted repos and add their PRs."""
    async with AsyncSessionLocal() as db:
        await set_delivery(db, org_id, bud_id, spec)
    return Response(status_code=204)


@router.post("/buds/{bud_id}/manual-cases", status_code=204, response_class=Response)
async def create_manual_cases(
    org_id: uuid.UUID, bud_id: uuid.UUID, spec: ManualCasesSpec
) -> Response:
    """Give the BUD pending manual test cases."""
    async with AsyncSessionLocal() as db:
        await set_manual_cases(db, org_id, bud_id, spec)
    return Response(status_code=204)


@router.post("/buds/{bud_id}/releases", status_code=204, response_class=Response)
async def create_release(org_id: uuid.UUID, bud_id: uuid.UUID, spec: ReleaseSpec) -> Response:
    """Record a release PR merged into UAT or prod for the BUD."""
    async with AsyncSessionLocal() as db:
        await record_release(db, org_id, bud_id, spec)
    return Response(status_code=204)
