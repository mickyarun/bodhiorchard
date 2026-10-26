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

"""Every leave type setting comes back as it was saved.

The dialog edits what the API returns, so a setting the read leaves out is
cleared by the next unrelated edit.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.schemas.leave_type import LeaveTypeWrite
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration

# A value other than the default for every setting.
SAVED = {
    "name": "Earned leave",
    "code": "EL",
    "annual_quota_days": "18",
    "accrual": "monthly",
    "is_paid": False,
    "is_encashable": True,
    "counts_toward_warning": False,
    "eligible_genders": ["female"],
    "auto_approve": True,
    "monthly_limit_days": "2",
    "stops_at_balance": True,
    "carry_forward_days": "5",
    "color_key": "swatch-3",
    "is_active": False,
}


def test_every_setting_is_covered() -> None:
    assert set(SAVED) == set(LeaveTypeWrite.model_fields)


async def test_saved_settings_come_back(client: AsyncClient, pg_session_factory: Factory) -> None:
    org, (hr,), casual = await setup_org(pg_session_factory, "Hr")
    await give_role(pg_session_factory, org, hr, "hr")
    saved = await client.put(f"/api/v1/leave/types/{casual}", json=SAVED, headers=as_user(hr, org))
    assert saved.status_code == 200, saved.text
    expected = LeaveTypeWrite.model_validate(SAVED).model_dump(mode="json")
    read = LeaveTypeWrite.model_validate(saved.json()).model_dump(mode="json")
    assert read == expected
    assert Decimal(read["carry_forward_days"]) == Decimal(5)
