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

"""The manual-test-case gate out of testing, through the real routes.

Leaving testing for UAT or prod needs every manual case in a terminal
result. Pending blocks it (and must leave no side effect behind);
skipped is terminal but records a ``qa_skip`` override; closing from
testing is allowed with cases still pending.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from tests.integration.bud_lifecycle_reads import (
    load_bud,
    timeline,
)
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_member,
    as_user,
    bud_in_testing,
    stub_externals,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("target", ["uat", "prod"])
async def test_pending_case_blocks_leaving_testing_with_no_side_effects(
    client: AsyncClient, pg_session_factory: Factory, target: str
) -> None:
    """400 names the pending case; status, timeline and history stay untouched."""
    org, bud_id = await bud_in_testing(pg_session_factory, "pass", "pending")
    pm = await add_member(pg_session_factory, org, "pm")

    with stub_externals() as ext:
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": target}, headers=as_user(pm, org)
        )

    assert res.status_code == 400
    assert "1 manual test case still pending (MTC-002)" in res.json()["detail"]
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.TESTING
    assert await timeline(pg_session_factory, bud_id, "status_change") == []
    ext.bg_estimate.assert_not_awaited()


async def test_pending_list_is_truncated_after_five_ids(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Seven pending cases: the first five are named, the rest summarised."""
    org, bud_id = await bud_in_testing(pg_session_factory, *(["pending"] * 7))
    pm = await add_member(pg_session_factory, org, "pm")

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "uat"}, headers=as_user(pm, org)
        )

    detail = res.json()["detail"]
    assert res.status_code == 400
    assert "7 manual test cases still pending" in detail
    assert "MTC-005 and 2 more" in detail
    assert "MTC-006" not in detail


async def test_all_terminal_results_advance_and_skips_are_recorded(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """pass/fail/blocked/skipped all count; the skipped ids land in a qa_skip override."""
    org, bud_id = await bud_in_testing(pg_session_factory, "pass", "fail", "blocked", "skipped")
    pm = await add_member(pg_session_factory, org, "pm")

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "uat"}, headers=as_user(pm, org)
        )

    assert res.status_code == 200
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.UAT
    overrides = await timeline(pg_session_factory, bud_id, "status_override")
    assert overrides == [
        {
            "kind": "qa_skip",
            "from": "testing",
            "to": "uat",
            "phase": "testing",
            "skipped_case_ids": ["MTC-004"],
        }
    ]


async def test_clean_exit_records_no_override(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Every case executed: no qa_skip override, one status_change."""
    org, bud_id = await bud_in_testing(pg_session_factory, "pass", "pass")
    pm = await add_member(pg_session_factory, org, "pm")

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "uat"}, headers=as_user(pm, org)
        )

    assert res.status_code == 200
    assert await timeline(pg_session_factory, bud_id, "status_override") == []
    assert await timeline(pg_session_factory, bud_id, "status_change") == [
        {"from": "testing", "to": "uat"}
    ]


async def test_closing_from_testing_ignores_pending_cases(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Closing abandons the BUD, so pending cases do not block it."""
    org, bud_id = await bud_in_testing(pg_session_factory, "pending")
    pm = await add_member(pg_session_factory, org, "pm")

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "closed"}, headers=as_user(pm, org)
        )

    assert res.status_code == 200
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.CLOSED
