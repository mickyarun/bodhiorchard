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

"""What closing a BUD through PATCH pays out, and what it must not do.

The assignee gets the 50 XP ``bud_completed`` award once; every other
commit / PR contributor gets 25 XP once; prod and then closed (the
auto-close path's shape) never pays twice; the XP aggregate always
matches the audit events. Closing never starts a repo scan.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from app.models.scan import Scan
from app.models.webhook_log import WebhookLog
from app.services import bud_closure
from tests.integration.bud_lifecycle_reads import (
    count_rows,
    xp_events,
    xp_ledger,
    xp_owner,
)
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_commit,
    add_member,
    as_user,
    new_org,
    stub_externals,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration

BUD_NUMBER = 41


async def _shipped_bud(
    factory: Factory, *, status: BUDStatus = BUDStatus.UAT, **fields: object
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Org, PM, assignee, one other contributor and a BUD both committed to.

    ``lead`` is the org's only developer, so the prod phase's round-robin
    auto-assignment keeps the BUD on them; ``helper`` (a designer who also
    committed) is a contributor only.
    """
    org = await new_org(factory)
    pm = await add_member(factory, org, "pm")
    lead = await add_member(factory, org, "lead", role="developer")
    helper = await add_member(factory, org, "helper", role="designer")
    bud_id = await add_bud(
        factory, org, number=BUD_NUMBER, status=status, assignee_id=lead, **fields
    )
    for user in (lead, helper, helper):
        await add_commit(factory, org, bud_id, user)
    return org, pm, lead, helper, bud_id


async def test_close_pays_assignee_and_contributors_exactly_once(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """One close, then a rejected second close: every award exists once."""
    org, pm, lead, helper, bud_id = await _shipped_bud(pg_session_factory)
    url, headers = f"/api/v1/buds/{bud_id}", as_user(pm, org)

    with stub_externals():
        first = await client.patch(url, json={"status": "closed"}, headers=headers)
        after_first = await xp_events(pg_session_factory, org)
        second = await client.patch(url, json={"status": "closed"}, headers=headers)

    assert (first.status_code, second.status_code) == (200, 400)
    assert after_first[f"bud:{BUD_NUMBER}"] == 50
    assert await xp_owner(pg_session_factory, org, f"bud:{BUD_NUMBER}") == lead
    assert after_first[f"bud_contrib:{BUD_NUMBER}:{helper}"] == 25
    # The assignee is paid through ``bud_completed`` only, never as a contributor.
    assert f"bud_contrib:{BUD_NUMBER}:{lead}" not in after_first
    assert await xp_events(pg_session_factory, org) == after_first
    for user in (lead, helper):
        total, from_events = await xp_ledger(pg_session_factory, org, user)
        assert total == from_events


async def test_prod_then_closed_does_not_pay_twice(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Hooks fire at prod and at closed; the second firing adds nothing."""
    org, pm, lead, helper, bud_id = await _shipped_bud(pg_session_factory)
    url, headers = f"/api/v1/buds/{bud_id}", as_user(pm, org)

    with stub_externals():
        to_prod = await client.patch(url, json={"status": "prod"}, headers=headers)
        at_prod = await xp_events(pg_session_factory, org)
        to_closed = await client.patch(url, json={"status": "closed"}, headers=headers)

    assert (to_prod.status_code, to_closed.status_code) == (200, 200)
    assert at_prod[f"bud:{BUD_NUMBER}"] == 50
    assert await xp_owner(pg_session_factory, org, f"bud:{BUD_NUMBER}") == lead
    assert at_prod[f"bud_contrib:{BUD_NUMBER}:{helper}"] == 25
    assert await xp_events(pg_session_factory, org) == at_prod
    total, from_events = await xp_ledger(pg_session_factory, org, helper)
    assert total == from_events == 25


async def test_close_without_assignee_pays_only_contributors(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """No assignee: no bud_completed award, every committer is a contributor."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    dev = await add_member(pg_session_factory, org, "dev", role="developer")
    bud_id = await add_bud(pg_session_factory, org, number=BUD_NUMBER, status=BUDStatus.UAT)
    await add_commit(pg_session_factory, org, bud_id, dev)

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "closed"}, headers=as_user(pm, org)
        )

    assert res.status_code == 200
    assert await xp_events(pg_session_factory, org) == {f"bud_contrib:{BUD_NUMBER}:{dev}": 25}


async def test_close_starts_no_repo_scan(client: AsyncClient, pg_session_factory: Factory) -> None:
    """Scans belong to the PR-merge webhook: closing leaves no scan or delivery behind.

    The scan entry points open their own app-database sessions, which the
    autouse ``app_database_blocked`` guard would also catch and fail on.
    """
    org, pm, _lead, _helper, bud_id = await _shipped_bud(pg_session_factory)

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "closed"}, headers=as_user(pm, org)
        )

    assert res.status_code == 200
    assert await count_rows(pg_session_factory, Scan, org) == 0
    assert await count_rows(pg_session_factory, WebhookLog, org) == 0
    # The closure module does not even import a scan trigger.
    for entry_point in ("start_scan", "publish_pr_merge_delivery", "trigger_scan"):
        assert not hasattr(bud_closure, entry_point)


@pytest.mark.parametrize(("opted_in", "expected_calls"), [(True, 1), (False, 0)])
async def test_learning_agent_spawns_only_on_closed_and_only_when_opted_in(
    client: AsyncClient, pg_session_factory: Factory, opted_in: bool, expected_calls: int
) -> None:
    """The prod firing never spawns it; the closed firing spawns it iff opted in."""
    org, pm, _lead, _helper, bud_id = await _shipped_bud(
        pg_session_factory, auto_generate_phases={"closed": opted_in}
    )
    url, headers = f"/api/v1/buds/{bud_id}", as_user(pm, org)
    spawn = AsyncMock(return_value=None)

    with stub_externals(), patch("app.services.bud_closure.create_agent_task_for_stage", spawn):
        await client.patch(url, json={"status": "prod"}, headers=headers)
        assert spawn.await_count == 0
        res = await client.patch(url, json={"status": "closed"}, headers=headers)

    assert res.status_code == 200
    assert spawn.await_count == expected_calls
    if expected_calls:
        assert spawn.await_args is not None
        assert spawn.await_args.args[1] == "closed"
        assert spawn.await_args.kwargs["triggered_by"] == pm
