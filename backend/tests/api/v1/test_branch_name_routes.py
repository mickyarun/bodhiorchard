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

"""Every route that stores a branch name answers 422 for an invalid one.

The request never reaches the handler, so nothing is written: the test
app has no database, and a handler run would fail loudly instead.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.api.v1 import settings_repos as repos_api
from app.api.v1 import setup as setup_api
from app.core.auth_deps import get_current_user, get_db
from app.core.permission_deps import PermissionSet, get_permission_set

HOSTILE = ["..", ".", "-x", "a..b", "main.lock", "a b", "x\n"]


async def _no_db() -> AsyncIterator[None]:
    yield None


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(repos_api.router, prefix="/api/v1/settings")
    app.include_router(setup_api.router, prefix="/api/v1/setup")
    app.dependency_overrides[get_db] = _no_db
    user = SimpleNamespace(id=uuid.uuid4(), must_change_password=False)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_permission_set] = lambda: PermissionSet(
        ids=frozenset({"settings:view", "settings:edit"}), is_owner=True
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


def _branch_field_errors(response: Any) -> list[str]:
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text
    return [str(err["loc"][-1]) for err in response.json()["detail"]]


@pytest.mark.parametrize("name", HOSTILE)
@pytest.mark.parametrize("field", ["mainBranch", "developBranch", "uatBranch"])
async def test_branch_update_refuses_a_bad_name(
    client: AsyncClient, name: str, field: str
) -> None:
    response = await client.patch(
        f"/api/v1/settings/repos/{uuid.uuid4()}/branches", json={field: name}
    )
    assert _branch_field_errors(response)


@pytest.mark.parametrize("name", HOSTILE)
async def test_bulk_onboard_refuses_a_bad_name(client: AsyncClient, name: str) -> None:
    response = await client.post(
        "/api/v1/settings/repos/bulk-onboard",
        json={"items": [{"fullName": "acme/widgets", "mainBranch": name}]},
    )
    assert "mainBranch" in _branch_field_errors(response)


@pytest.mark.parametrize("name", HOSTILE)
@pytest.mark.parametrize(
    "body_for",
    [
        lambda name: {"installableItems": [{"fullName": "acme/widgets", "mainBranch": name}]},
        lambda name: {"sourceCode": {"repos": [{"path": "/repo", "mainBranch": name}]}},
        lambda name: {"sourceCode": {"repos": [{"path": "/repo", "developBranch": name}]}},
    ],
)
async def test_setup_finalize_refuses_a_bad_name(
    client: AsyncClient, name: str, body_for: Any
) -> None:
    response = await client.post("/api/v1/setup/finalize-with-repos", json=body_for(name))
    assert _branch_field_errors(response)
