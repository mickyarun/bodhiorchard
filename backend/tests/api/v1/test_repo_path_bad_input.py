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

"""Malformed repository paths are client errors, never a 500.

Two inputs used to escape as exceptions: a NUL byte, which makes
``os.path.realpath`` raise ``ValueError``, and a name longer than the
filesystem allows, which makes ``Path.exists`` raise ``OSError``. The
first is now a validation error; the second reads as a missing path.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.api.v1 import settings_repos as repos_api
from app.api.v1 import settings_repos_local as local_api
from app.core.auth_deps import get_current_user, get_db
from app.core.permission_deps import PermissionSet, get_permission_set
from app.schemas.setup import SetupSourceCode
from app.services import setup_finalize_legacy as legacy

BROWSE = "/api/v1/settings/repos/browse-directories"
BRANCHES = "/api/v1/settings/repos/local-branches"
ADD = "/api/v1/settings/repos"
TOO_LONG = "a" * 300


async def _no_db() -> AsyncIterator[None]:
    yield None


@pytest.fixture
def root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = (tmp_path / "home").resolve()
    path.mkdir()
    for module in (local_api, repos_api, legacy):
        monkeypatch.setattr(module, "picker_roots", lambda: (path,))
    return path


@pytest.fixture
async def editor() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(local_api.router, prefix="/api/v1/settings")
    app.include_router(repos_api.router, prefix="/api/v1/settings")
    app.dependency_overrides[get_db] = _no_db
    user = SimpleNamespace(id=uuid.uuid4(), must_change_password=False)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_permission_set] = lambda: PermissionSet(
        ids=frozenset({"settings:view", "settings:edit"}), is_owner=False
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.parametrize("url", [BROWSE, BRANCHES])
async def test_a_nul_byte_is_a_validation_error(editor: AsyncClient, root: Path, url: str) -> None:
    response = await editor.get(url, params={"path": f"{root}/a\x00b"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_a_nul_byte_in_add_by_path_is_a_validation_error(
    editor: AsyncClient, root: Path
) -> None:
    response = await editor.post(ADD, json={"path": f"{root}/a\x00b"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(
    ("method", "url", "expected"),
    [
        ("get", BROWSE, status.HTTP_404_NOT_FOUND),
        ("get", BRANCHES, status.HTTP_400_BAD_REQUEST),
        ("post", ADD, status.HTTP_400_BAD_REQUEST),
    ],
)
async def test_a_name_too_long_for_the_filesystem_reads_as_missing(
    editor: AsyncClient, root: Path, method: str, url: str, expected: int
) -> None:
    path = str(root / TOO_LONG)
    if method == "get":
        response = await editor.get(url, params={"path": path})
    else:
        response = await editor.post(url, json={"path": path})
    assert response.status_code == expected


async def test_finalize_skips_a_too_long_name_and_keeps_the_rest(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = root / "svc"
    subprocess.run(["git", "init", "-q", str(good)], check=True, capture_output=True)
    registered: list[str] = []

    class _Repos:
        def __init__(self, _db: object, *, org_id: uuid.UUID) -> None:
            pass

        async def upsert(self, path: str, _name: str) -> SimpleNamespace:
            registered.append(path)
            return SimpleNamespace(id=uuid.uuid4(), main_branch=None, develop_branch=None)

    class _Db:
        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            return None

    async def _kick(**_: Any) -> tuple[None, None]:
        return None, None

    monkeypatch.setattr(legacy, "TrackedRepoRepository", _Repos)
    monkeypatch.setattr(legacy, "kick_off_onboard_scan", _kick)
    source = SetupSourceCode.model_validate(
        {"repos": [{"path": str(root / TOO_LONG)}, {"path": str(good)}]}
    )

    await legacy.finalize_legacy_source_code(
        org=SimpleNamespace(id=uuid.uuid4(), slug="acme"),  # type: ignore[arg-type]
        source_code=source,
        db=_Db(),  # type: ignore[arg-type]
    )

    assert registered == [str(good)]


def test_finalize_rejects_a_nul_byte_at_validation() -> None:
    with pytest.raises(ValueError):
        SetupSourceCode.model_validate({"repos": [{"path": "/home/a\x00b"}]})
