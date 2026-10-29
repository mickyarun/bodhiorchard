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

"""``/__e2e`` seeding routes: an org with its people, then content per area.

Only :mod:`tests.e2e_stack.serve` mounts these, on a server bound to
loopback and backed by a throwaway database.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from app.database import AsyncSessionLocal
from tests.e2e_stack.seed_content import add_features, open_quiz
from tests.e2e_stack.seed_org import seed_org
from tests.e2e_stack.specs import FeaturesSpec, OrgSpec, QuizSpec, SeededOrg

router = APIRouter(prefix="/__e2e/orgs", tags=["e2e"])


@router.post("", response_model=SeededOrg, response_model_by_alias=True)
async def create_org(spec: OrgSpec) -> SeededOrg:
    """Seed an org (or extend the oldest one) with members and leave types."""
    async with AsyncSessionLocal() as db:
        return await seed_org(db, spec)


@router.post("/{org_id}/features", status_code=204, response_class=Response)
async def create_features(org_id: uuid.UUID, spec: FeaturesSpec) -> Response:
    """Add features to the org's registry."""
    async with AsyncSessionLocal() as db:
        await add_features(db, org_id, spec)
    return Response(status_code=204)


@router.post("/{org_id}/quiz", status_code=204, response_class=Response)
async def create_open_quiz(org_id: uuid.UUID, spec: QuizSpec) -> Response:
    """Open today's quiz for the org."""
    async with AsyncSessionLocal() as db:
        await open_quiz(db, org_id, spec)
    return Response(status_code=204)
