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

"""The QA tab (manual results) and the QA role's limits on PATCH.

QA records results through ``/qa/manual-results`` and may then promote
out of testing; any other transition or field is a 403 for a
``buds:test``-only caller. Results are org-scoped.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from tests.integration.bud_lifecycle_reads import (
    load_bud,
)
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_member,
    as_user,
    bud_in_testing,
    manual_cases,
    new_org,
    stub_externals,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration


async def test_qa_marks_cases_then_passes_the_gate(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """QA (buds:test only) records results through the QA tab, then promotes."""
    org, bud_id = await bud_in_testing(pg_session_factory, "pending", "pending")
    qa = await add_member(pg_session_factory, org, "Quinn", role="qa")
    headers = as_user(qa, org)

    with stub_externals():
        blocked = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "uat"}, headers=headers
        )
        for case_id, result in (("MTC-001", "pass"), ("MTC-002", "blocked")):
            marked = await client.patch(
                f"/api/v1/buds/{bud_id}/qa/manual-results",
                json={"test_case_id": case_id, "result": result, "notes": "ok"},
                headers=headers,
            )
            assert marked.status_code == 200
        summary = await client.get(f"/api/v1/buds/{bud_id}/qa/summary", headers=headers)
        promoted = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "uat"}, headers=headers
        )

    assert blocked.status_code == 400
    assert summary.json()["manual_pass"] == 1
    assert summary.json()["manual_blocked"] == 1
    assert summary.json()["manual_pending"] == 0
    assert promoted.status_code == 200
    cases = (await load_bud(pg_session_factory, bud_id)).qa_manual_cases or []
    assert [c["tester_name"] for c in cases] == ["Quinn", "Quinn"]


async def test_reverting_a_case_to_pending_blocks_the_gate_again(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A pass reverted to pending clears its attribution and re-arms the gate."""
    org, bud_id = await bud_in_testing(pg_session_factory, "pass")
    pm = await add_member(pg_session_factory, org, "pm")
    headers = as_user(pm, org)

    with stub_externals():
        await client.patch(
            f"/api/v1/buds/{bud_id}/qa/manual-results",
            json={"test_case_id": "MTC-001", "result": "pending"},
            headers=headers,
        )
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "prod"}, headers=headers
        )

    assert res.status_code == 400
    case = ((await load_bud(pg_session_factory, bud_id)).qa_manual_cases or [])[0]
    assert (case["result"], case["tester_name"], case["tested_at"]) == ("pending", None, None)


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (BUDStatus.TESTING, {"status": "development"}),
        (BUDStatus.UAT, {"status": "prod"}),
        (BUDStatus.TESTING, {"title": "QA renamed it"}),
        (BUDStatus.TESTING, {"status": "uat", "title": "and renamed it"}),
    ],
)
async def test_qa_role_is_limited_to_promoting_out_of_testing(
    client: AsyncClient, pg_session_factory: Factory, status: BUDStatus, payload: dict[str, str]
) -> None:
    """buds:test-only callers get 403 for any other transition or field."""
    org = await new_org(pg_session_factory)
    qa = await add_member(pg_session_factory, org, "qa", role="qa")
    bud_id = await add_bud(
        pg_session_factory, org, status=status, qa_manual_cases=manual_cases("pass")
    )

    with stub_externals():
        res = await client.patch(f"/api/v1/buds/{bud_id}", json=payload, headers=as_user(qa, org))

    assert res.status_code == 403
    bud = await load_bud(pg_session_factory, bud_id)
    assert (bud.status, bud.title) == (status, "BUD 1")


async def test_manual_results_are_org_scoped_and_validate_the_case(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Other org gets 404; an unknown case id is 404 and writes nothing."""
    org, bud_id = await bud_in_testing(pg_session_factory, "pending")
    pm = await add_member(pg_session_factory, org, "pm")
    other_org = await new_org(pg_session_factory)
    outsider = await add_member(pg_session_factory, other_org, "outsider")
    url = f"/api/v1/buds/{bud_id}/qa/manual-results"

    foreign = await client.patch(
        url,
        json={"test_case_id": "MTC-001", "result": "pass"},
        headers=as_user(outsider, other_org),
    )
    unknown = await client.patch(
        url, json={"test_case_id": "MTC-999", "result": "pass"}, headers=as_user(pm, org)
    )

    assert (foreign.status_code, unknown.status_code) == (404, 404)
    case = ((await load_bud(pg_session_factory, bud_id)).qa_manual_cases or [])[0]
    assert case["result"] == "pending"
