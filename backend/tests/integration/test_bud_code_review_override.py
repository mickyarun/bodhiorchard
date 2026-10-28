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

"""``POST /buds/{id}/code-review/override`` (force code_review -> testing).

The override records its reason and a status change, moves the BUD to
testing and asks for the QA agent. It needs a real reason, a BUD that is
actually in code_review, ``buds:edit``, and the caller's own org.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

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
    stub_externals,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration

REASON = "Docs-only change, merged by hand"


@contextmanager
def _override_stubs(factory: Factory) -> Iterator[AsyncMock]:
    """Externals stubbed, the inline estimator on the test DB, the agent spawn mocked."""
    spawn = AsyncMock(return_value=None)
    with (
        stub_externals(),
        patch("app.api.v1.bud.AsyncSessionLocal", factory),
        patch("app.api.v1.bud.create_agent_task_for_stage", spawn),
    ):
        yield spawn


async def _post(
    client: AsyncClient, factory: Factory, bud_id: uuid.UUID, headers: dict[str, str], body: object
) -> int:
    """POST the override; return the status code."""
    with _override_stubs(factory):
        res = await client.post(
            f"/api/v1/buds/{bud_id}/code-review/override", json=body, headers=headers
        )
    return res.status_code


async def test_override_moves_to_testing_and_records_the_reason(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """200, status testing, override + status change on the timeline, QA agent asked."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.CODE_REVIEW)

    with _override_stubs(pg_session_factory) as spawn:
        res = await client.post(
            f"/api/v1/buds/{bud_id}/code-review/override",
            json={"reason": REASON},
            headers=as_user(pm, org),
        )

    assert res.status_code == 200
    assert res.json()["status"] == "testing"
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.TESTING
    [override] = await timeline(pg_session_factory, bud_id, "code_review_override")
    assert (override["reason"], override["to"], override["triggered_by"]) == (
        REASON,
        "testing",
        str(pm),
    )
    changes = await timeline(pg_session_factory, bud_id, "status_change")
    assert [(c["from"], c["to"], c["auto"]) for c in changes] == [
        ("code_review", "testing", False)
    ]
    assert spawn.await_count == 1
    assert spawn.await_args is not None
    assert spawn.await_args.args[1] == "testing"
    assert spawn.await_args.kwargs["force"] is True


@pytest.mark.parametrize("body", [{"reason": "too short"}, {}, {"reason": "x" * 2001}])
async def test_override_needs_a_real_reason(
    client: AsyncClient, pg_session_factory: Factory, body: dict[str, str]
) -> None:
    """Reasons under 10 or over 2000 characters, or missing, are 422."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.CODE_REVIEW)

    assert await _post(client, pg_session_factory, bud_id, as_user(pm, org), body) == 422
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.CODE_REVIEW


@pytest.mark.parametrize("status", [BUDStatus.DEVELOPMENT, BUDStatus.TESTING, BUDStatus.CLOSED])
async def test_override_only_from_code_review(
    client: AsyncClient, pg_session_factory: Factory, status: BUDStatus
) -> None:
    """Any other status is a 409 and nothing is recorded."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=status)

    code = await _post(client, pg_session_factory, bud_id, as_user(pm, org), {"reason": REASON})

    assert code == 409
    assert (await load_bud(pg_session_factory, bud_id)).status is status
    assert await timeline(pg_session_factory, bud_id, "code_review_override") == []


async def test_override_is_org_scoped_and_needs_edit(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """QA in the same org gets 403; a PM of another org gets 404."""
    org = await new_org(pg_session_factory)
    qa = await add_member(pg_session_factory, org, "qa", role="qa")
    other_org = await new_org(pg_session_factory)
    outsider = await add_member(pg_session_factory, other_org, "outsider")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.CODE_REVIEW)
    body = {"reason": REASON}

    qa_code = await _post(client, pg_session_factory, bud_id, as_user(qa, org), body)
    outsider_code = await _post(
        client, pg_session_factory, bud_id, as_user(outsider, other_org), body
    )

    assert (qa_code, outsider_code) == (403, 404)
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.CODE_REVIEW
