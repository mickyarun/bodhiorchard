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

"""``GET /settings/ai/capabilities?base_url=`` lists the models of a typed host.

AI settings sends the address being typed, so the page can show that host's
models before it is saved. The permission check for the probe was called
with the wrong arguments, so every such request answered 500 and the page
never listed a self-hosted server's models. Found by the browser tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import ai_settings
from tests.fakes.seed import auth_headers, seed_member, seed_org

pytestmark = pytest.mark.integration

TYPED_HOST = "http://gpu-box.internal:11434"


@pytest.fixture
def probed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Answer the model listing in place of a real host; record where it was sent."""
    targets: list[str] = []

    async def _models(target: str, _api_key: str | None) -> list[str]:
        targets.append(target)
        return ["llama3.1:8b"]

    monkeypatch.setattr(ai_settings, "list_tool_models", _models)
    return targets


async def test_an_owner_sees_the_models_of_the_typed_host(
    pg_session_factory: async_sessionmaker[AsyncSession], client: AsyncClient, probed: list[str]
) -> None:
    org = await seed_org(pg_session_factory)

    response = await client.get(
        "/api/v1/settings/ai/capabilities",
        params={"base_url": TYPED_HOST},
        headers=auth_headers(org.owner_id, org.org_id),
    )

    assert response.status_code == 200
    assert probed == [TYPED_HOST]
    ollama = next(p for p in response.json()["providers"] if p["provider"] == "ollama")
    assert ollama["models"] == [{"id": "llama3.1:8b", "label": "llama3.1:8b"}]


async def test_probing_a_typed_host_needs_integrations_configure(
    pg_session_factory: async_sessionmaker[AsyncSession], client: AsyncClient, probed: list[str]
) -> None:
    org = await seed_org(pg_session_factory)
    developer = await seed_member(pg_session_factory, org.org_id, "dev", role="developer")

    response = await client.get(
        "/api/v1/settings/ai/capabilities",
        params={"base_url": TYPED_HOST},
        headers=auth_headers(developer, org.org_id),
    )

    assert response.status_code == 403
    assert probed == []
