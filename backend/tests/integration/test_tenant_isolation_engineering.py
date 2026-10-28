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

"""Another org's engineering rows can't be read, changed or deleted over HTTP.

The caller is org A's owner, who passes every permission check, so a
refusal can only come from tenant scoping. Each probe must answer 404
(the row doesn't exist as far as org A is concerned) and org B's rows must
be exactly as they were afterwards.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api.v1 import bug_attachments
from tests.integration.auth_tenancy_snapshot import snapshot
from tests.integration.auth_tenancy_support import TenantRows, new_tenant, seed_rows
from tests.integration.leave_support import Factory, as_user

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fake_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Attachment bytes live in object storage; the seeded rows point at a fake."""
    storage = MagicMock(
        download=AsyncMock(return_value=(b"trace", "text/plain")), delete=AsyncMock()
    )
    monkeypatch.setattr(bug_attachments, "get_file_storage", MagicMock(return_value=storage))


def _probes(b: TenantRows) -> list[tuple[str, str, dict[str, Any] | None]]:
    """(method, path, json body) aimed at org B's rows."""
    return [
        ("GET", f"/api/v1/buds/{b.bud}", None),
        ("GET", f"/api/v1/buds/{b.bud}/versions", None),
        ("GET", f"/api/v1/buds/{b.bud}/todos", None),
        ("PATCH", f"/api/v1/buds/{b.bud}", {"title": "Taken over"}),
        ("POST", f"/api/v1/buds/{b.bud}/todos", {"title": "Planted", "phase": "development"}),
        ("DELETE", f"/api/v1/buds/{b.bud}", None),
        ("GET", f"/api/v1/bugs/{b.bug}", None),
        ("PATCH", f"/api/v1/bugs/{b.bug}", {"title": "Taken over"}),
        ("GET", f"/api/v1/bugs/{b.bug}/comments", None),
        ("POST", f"/api/v1/bugs/{b.bug}/comments", {"body": "Planted"}),
        ("PATCH", f"/api/v1/bugs/{b.bug}/comments/{b.comment}", {"body": "Taken over"}),
        ("DELETE", f"/api/v1/bugs/{b.bug}/comments/{b.comment}", None),
        ("GET", f"/api/v1/bugs/{b.bug}/attachments", None),
        ("GET", f"/api/v1/bugs/{b.bug}/attachments/{b.attachment}", None),
        ("DELETE", f"/api/v1/bugs/{b.bug}/attachments/{b.attachment}", None),
        ("GET", f"/api/v1/features/{b.feature}", None),
        ("GET", f"/api/v1/design-systems/{b.design_system}", None),
        ("PUT", f"/api/v1/design-systems/{b.design_system}", {"custom_content": "Taken"}),
        ("POST", f"/api/v1/design-systems/{b.design_system}/reset-customisations", None),
        ("DELETE", f"/api/v1/design-systems/{b.design_system}", None),
        ("PATCH", f"/api/v1/settings/repos/{b.repo}/status", {"status": "ignored"}),
        ("GET", f"/api/v1/teams/{b.team}", None),
        ("PATCH", f"/api/v1/teams/{b.team}", {"name": "Taken over"}),
        ("DELETE", f"/api/v1/teams/{b.team}", None),
        ("PATCH", f"/api/v1/quiz/review/{b.question}", {"prompt": "Taken over?"}),
        ("POST", f"/api/v1/quiz/review/{b.question}/approve", {}),
        ("POST", f"/api/v1/quiz/review/{b.question}/reject", None),
    ]


async def test_org_a_owner_cannot_touch_org_b_engineering_rows(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    a = await new_tenant(pg_session_factory)
    b = await new_tenant(pg_session_factory)
    rows = await seed_rows(pg_session_factory, b)
    before = await snapshot(pg_session_factory, rows)
    headers = as_user(a.owner, a.org)

    answers = {}
    for method, path, body in _probes(rows):
        response = await client.request(method, path, json=body, headers=headers)
        answers[f"{method} {path}"] = response.status_code
    assert {k: v for k, v in answers.items() if v != 404} == {}
    assert await snapshot(pg_session_factory, rows) == before


async def test_org_b_owner_reaches_the_same_rows(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Control: every probe, writes included, succeeds in its own org.

    Each probe gets a fresh org so a delete can't break the probes after it.
    """
    b = await new_tenant(pg_session_factory)
    count = len(_probes(await seed_rows(pg_session_factory, b)))
    failed = {}
    for index in range(count):
        tenant = await new_tenant(pg_session_factory)
        method, path, body = _probes(await seed_rows(pg_session_factory, tenant))[index]
        headers = as_user(tenant.owner, tenant.org)
        response = await client.request(method, path, json=body, headers=headers)
        if response.status_code >= 300:
            failed[f"{method} {path}"] = (response.status_code, response.text[:200])
    assert failed == {}


def _listed(rows: TenantRows) -> dict[str, uuid.UUID]:
    """Collection route -> the seeded row it should list."""
    return {
        "/api/v1/buds/": rows.bud,
        "/api/v1/bugs": rows.bug,
        "/api/v1/features": rows.feature,
        "/api/v1/design-systems/": rows.design_system,
        "/api/v1/settings/repos": rows.repo,
        "/api/v1/teams": rows.team,
        "/api/v1/quiz/review": rows.question,
    }


async def test_lists_show_own_rows_and_never_another_orgs(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    a = await new_tenant(pg_session_factory)
    mine = _listed(await seed_rows(pg_session_factory, a))
    b = await new_tenant(pg_session_factory)
    theirs = _listed(await seed_rows(pg_session_factory, b))
    headers = as_user(a.owner, a.org)
    for path, own_id in mine.items():
        response = await client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)
        assert str(own_id) in response.text, path
        assert str(theirs[path]) not in response.text, path


async def test_a_bud_timeline_shows_only_the_callers_org_events(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """The timeline route doesn't 404 a foreign BUD, but it must come back empty."""
    a = await new_tenant(pg_session_factory)
    b = await new_tenant(pg_session_factory)
    rows = await seed_rows(pg_session_factory, b)
    path = f"/api/v1/buds/{rows.bud}/timeline"
    foreign = await client.get(path, headers=as_user(a.owner, a.org))
    assert (foreign.status_code, foreign.json()) == (200, [])
    own = await client.get(path, headers=as_user(b.owner, b.org))
    assert [e["event_type"] for e in own.json()] == ["created"]
