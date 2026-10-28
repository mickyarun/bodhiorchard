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

"""Manual estimate overrides through ``/buds/{id}/estimates``.

An override needs a reason and a phase the org actually runs, is
visible in the estimates and the history, moves the current-phase
deadline only for the BUD's own phase, and is org-scoped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from tests.integration.bud_lifecycle_reads import load_bud, timeline
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_member,
    as_user,
    new_org,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration

# A whole day comfortably in the future, relative to the run date.
TARGET_DAY = (datetime.now(UTC) + timedelta(days=400)).date()
WHEN = datetime.combine(TARGET_DAY, time(), tzinfo=UTC).isoformat()


async def _setup(
    factory: Factory, config: dict[str, object] | None = None
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """Org (optionally configured), a development BUD and a PM's headers."""
    org = await new_org(factory, config=config)
    pm = await add_member(factory, org, "pm")
    bud_id = await add_bud(factory, org, status=BUDStatus.DEVELOPMENT)
    return org, bud_id, as_user(pm, org)


async def test_override_is_visible_everywhere(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Estimates, history, timeline and the phase deadline all reflect it."""
    _org, bud_id, headers = await _setup(pg_session_factory)
    url = f"/api/v1/buds/{bud_id}/estimates"

    res = await client.patch(
        f"{url}/development",
        json={"estimated_completion": WHEN, "reason": "Vendor delay"},
        headers=headers,
    )
    estimates = await client.get(url, headers=headers)
    history = await client.get(f"{url}/history", headers=headers)

    assert res.status_code == 200
    assert (res.json()["source"], res.json()["override_reason"]) == ("override", "Vendor delay")
    [phase] = [p for p in estimates.json()["phases"] if p["phase"] == "development"]
    assert phase["estimated_completion"].startswith(TARGET_DAY.isoformat())
    assert phase["confidence"] == 1.0
    assert [h["trigger"] for h in history.json()] == ["manual"]
    [event] = await timeline(pg_session_factory, bud_id, "estimate_overridden")
    assert (event["phase"], event["reason"], event["previous_date"]) == (
        "development",
        "Vendor delay",
        None,
    )
    bud = await load_bud(pg_session_factory, bud_id)
    assert bud.current_phase_deadline is not None
    assert bud.current_phase_deadline.date() == TARGET_DAY


async def test_overriding_another_phase_leaves_the_current_deadline(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Only the BUD's own phase drives ``current_phase_deadline``; prod drives p70."""
    _org, bud_id, headers = await _setup(pg_session_factory)

    res = await client.patch(
        f"/api/v1/buds/{bud_id}/estimates/prod",
        json={"estimated_completion": WHEN, "reason": "Release train"},
        headers=headers,
    )

    assert res.status_code == 200
    bud = await load_bud(pg_session_factory, bud_id)
    assert bud.current_phase_deadline is None
    assert bud.prod_p70_date is not None


@pytest.mark.parametrize(
    ("config", "phase", "body", "code"),
    [
        ({"bud_stages": {"uatEnabled": False}}, "uat", {"reason": "x"}, 400),
        (None, "closed", {"reason": "x"}, 400),
        (None, "nonsense", {"reason": "x"}, 400),
        (None, "development", {"reason": ""}, 422),
        (None, "development", {}, 422),
    ],
)
async def test_invalid_overrides_are_rejected_and_write_nothing(
    client: AsyncClient,
    pg_session_factory: Factory,
    config: dict[str, object] | None,
    phase: str,
    body: dict[str, str],
    code: int,
) -> None:
    """Disabled / non-pipeline phases are 400; a missing or empty reason is 422."""
    _org, bud_id, headers = await _setup(pg_session_factory, config)

    res = await client.patch(
        f"/api/v1/buds/{bud_id}/estimates/{phase}",
        json={"estimated_completion": WHEN, **body},
        headers=headers,
    )

    assert res.status_code == code
    assert (await load_bud(pg_session_factory, bud_id)).estimated_dates is None
    assert await timeline(pg_session_factory, bud_id, "estimate_overridden") == []


async def test_estimates_are_org_scoped_and_override_needs_edit(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Outsiders get 404 on every route; a same-org viewer may read but not override."""
    org, bud_id, _headers = await _setup(pg_session_factory)
    other_org = await new_org(pg_session_factory)
    outsider = as_user(await add_member(pg_session_factory, other_org, "outsider"), other_org)
    viewer = as_user(await add_member(pg_session_factory, org, "viewer", role="viewer"), org)
    url = f"/api/v1/buds/{bud_id}/estimates"
    body = {"estimated_completion": WHEN, "reason": "x"}

    outsider_codes = [
        (await client.get(url, headers=outsider)).status_code,
        (await client.get(f"{url}/history", headers=outsider)).status_code,
        (await client.patch(f"{url}/development", json=body, headers=outsider)).status_code,
    ]
    viewer_read = await client.get(url, headers=viewer)
    viewer_write = await client.patch(f"{url}/development", json=body, headers=viewer)

    assert outsider_codes == [404, 404, 404]
    assert (viewer_read.status_code, viewer_write.status_code) == (200, 403)
    assert (await load_bud(pg_session_factory, bud_id)).estimated_dates is None
