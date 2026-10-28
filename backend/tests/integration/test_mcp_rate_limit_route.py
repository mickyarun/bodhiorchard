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

"""A throttled tool call is refused with 429 and still audited.

The per-client cap is lowered to two units so the third unit-cost call
overflows without making sixty requests; redis is the in-memory stand-in.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.mcp import rate_limit
from tests.integration.mcp_seed import make_tenant
from tests.integration.mcp_support import (
    Factory,
    audit_rows,
    call,
    mcp_env,  # noqa: F401
)
from tests.mcp.rate_limit_support import install_fake_redis

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("mcp_env")]


async def test_throttled_call_is_429_with_an_audit_row(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Two calls pass, the third is 429 and recorded; the next minute passes again."""
    redis = install_fake_redis(monkeypatch)
    monkeypatch.setattr(rate_limit, "BUCKET_UNITS_PER_MINUTE", 2)
    tenant = await make_tenant(pg_session_factory)

    statuses = [
        (await call(client, tenant.token, "get_bud_context")).status_code for _ in range(2)
    ]
    throttled = await call(client, tenant.token, "get_bud_context", {"query": "tags"})
    redis.minute += 1
    later = await call(client, tenant.token, "get_bud_context")

    assert statuses == [200, 200]
    assert throttled.status_code == 429
    assert throttled.headers["retry-after"] == "60"
    assert later.status_code == 200
    rows = await audit_rows(pg_session_factory, tenant.org_id)
    assert sorted(r.status_code for r in rows) == [200, 200, 200, 429]
    (limited,) = [r for r in rows if r.status_code == 429]
    assert (limited.tool_name, limited.params) == ("get_bud_context", {"query": "tags"})
