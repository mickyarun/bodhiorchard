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

"""Every people route (leave, employees) is marked uncacheable.

A new leave or employee route mounted without the no-store dependency
fails here, so reasons and personal details never land in a browser or
proxy cache.
"""

import pytest
from fastapi import Response
from fastapi.routing import APIRoute

from app.api.router import api_router
from app.core.http_cache import no_store

PEOPLE_PREFIXES = ("/api/v1/leave", "/api/v1/employees", "/api/v1/offices")


def _people_routes() -> list[APIRoute]:
    return [
        r
        for r in api_router.routes
        if isinstance(r, APIRoute) and r.path.startswith(PEOPLE_PREFIXES)
    ]


def test_people_routes_exist() -> None:
    assert len(_people_routes()) > 20


def test_every_people_route_is_no_store() -> None:
    missing = [
        r.path
        for r in _people_routes()
        if not any(d.dependency is no_store for d in r.dependencies)
    ]
    assert missing == []


@pytest.mark.asyncio
async def test_no_store_sets_headers() -> None:
    response = Response()
    await no_store(response)
    assert response.headers["Cache-Control"] == "no-store, private"
    assert response.headers["Pragma"] == "no-cache"
