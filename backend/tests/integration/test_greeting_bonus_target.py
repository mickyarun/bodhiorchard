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

"""The greeting bonus pays only for greeting another member of your org.

It is keyed on ``(greeter, target)``, so an unchecked target let anyone mint
skill points without limit by sending a new string each time.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.developer_xp import DeveloperXP
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
GREET = "/api/v1/xp/claim-greeting-bonus"


async def _skill_points(factory: Factory, org: uuid.UUID, user: uuid.UUID) -> float:
    async with factory() as db:
        value = await db.scalar(
            select(DeveloperXP.skill_points).where(
                DeveloperXP.org_id == org, DeveloperXP.user_id == user
            )
        )
        return float(value or 0)


async def test_only_another_member_of_your_org_can_be_greeted_for_points(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Yourself, a made-up id, a non-uuid and another org's member earn nothing."""
    org, (dev, colleague), _ = await setup_org(pg_session_factory, "Dev", "Colleague")
    _other, (outsider,), _ = await setup_org(pg_session_factory, "Outsider")
    await give_role(pg_session_factory, org, dev, "developer")
    headers = as_user(dev, org)
    refused = {
        str(dev): 400,
        "not-a-user": 400,
        str(uuid.uuid4()): 404,
        str(outsider): 404,
    }
    for target, expected in refused.items():
        response = await client.post(GREET, json={"target_user_id": target}, headers=headers)
        assert response.status_code == expected, target
    assert await _skill_points(pg_session_factory, org, dev) == 0
    ok = await client.post(GREET, json={"target_user_id": str(colleague)}, headers=headers)
    assert ok.json() == {"awarded": True, "skill_points": 0.25, "sp_earned": 0.25}
