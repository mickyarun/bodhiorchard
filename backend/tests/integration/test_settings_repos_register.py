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

"""Registering a repo by path and by clone, end to end on Postgres.

Paths live under a picker root in ``tmp_path``. The clone goes through
the real cloner and a real git, with the GitHub URL rewritten to a bare
repository in ``tmp_path``, so nothing touches the network.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.v1 import settings_repos
from app.config import settings as app_settings
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.services import repo_cloner
from tests.api.v1.repo_path_support import init_repo, run_git
from tests.integration.settings_support import Factory, make_org

pytestmark = pytest.mark.integration

REPOS = "/api/v1/settings/repos"


@pytest.fixture
def root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = (tmp_path / "home").resolve()
    path.mkdir()
    monkeypatch.setattr(settings_repos, "picker_roots", lambda: (path,))
    monkeypatch.setattr(settings_repos, "delete_key", _no_cache)
    monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
    return path


async def _no_cache(_key: str) -> None:
    return None


async def _rows(factory: Factory, org_id: uuid.UUID) -> list[TrackedRepository]:
    async with factory() as db:
        return list(
            await db.scalars(select(TrackedRepository).where(TrackedRepository.org_id == org_id))
        )


async def test_add_by_path_detects_branches_and_a_readd_reactivates(
    client: AsyncClient, pg_session_factory: Factory, root: Path
) -> None:
    org = await make_org(pg_session_factory)
    repo = init_repo(root / "café-api", "develop")

    added = await client.post(REPOS, headers=org.owner.headers, json={"path": str(repo)})
    await client.request("DELETE", REPOS, headers=org.owner.headers, json={"path": str(repo)})
    again = await client.post(
        REPOS, headers=org.owner.headers, json={"path": f"{repo}/../café-api"}
    )

    assert added.status_code == again.status_code == 200, added.text
    (row,) = await _rows(pg_session_factory, org.id)
    assert (row.name, row.path, row.status) == ("café-api", str(repo), RepoStatus.ACTIVE)
    assert (row.main_branch, row.develop_branch) == ("main", "develop")


@pytest.mark.parametrize(
    ("name", "detail"),
    [("missing", "does not exist"), ("notes.txt", "not a git repository")],
)
async def test_add_by_path_refuses_what_is_not_a_checkout(
    client: AsyncClient, pg_session_factory: Factory, root: Path, name: str, detail: str
) -> None:
    org = await make_org(pg_session_factory)
    (root / "notes.txt").write_text("x")
    response = await client.post(REPOS, headers=org.owner.headers, json={"path": str(root / name)})
    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert await _rows(pg_session_factory, org.id) == []


async def test_a_developer_cannot_add_by_path(
    client: AsyncClient, pg_session_factory: Factory, root: Path
) -> None:
    org = await make_org(pg_session_factory)
    repo = init_repo(root / "svc")
    response = await client.post(REPOS, headers=org.developer.headers, json={"path": str(repo)})
    assert response.status_code == 403
    assert await _rows(pg_session_factory, org.id) == []


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A bare repo standing in for github.com/acme/widgets."""
    bare = tmp_path / "widgets.git"
    run_git("init", "-q", "--bare", "-b", "trunk", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    run_git("clone", "-q", str(bare), str(seed), cwd=tmp_path)
    run_git("commit", "-q", "--allow-empty", "-m", "one", cwd=seed)
    run_git("push", "-q", "origin", "HEAD:trunk", "HEAD:develop", cwd=seed)
    real = repo_cloner._run_git

    async def _local(args: list[str], **kwargs: Any) -> tuple[int, str, str]:
        swapped = [str(bare) if a.startswith("https://") else a for a in args]
        return await real(swapped, **kwargs)

    monkeypatch.setattr(repo_cloner, "_run_git", _local)
    return bare


async def test_clone_registers_the_checkout_under_the_orgs_folder(
    client: AsyncClient, pg_session_factory: Factory, root: Path, github: Path
) -> None:
    org = await make_org(pg_session_factory)
    body = {"url": "https://github.com/acme/widgets.git", "pat": "ghp_never_echoed"}

    response = await client.post(f"{REPOS}/clone", headers=org.owner.headers, json=body)

    assert response.status_code == 200, response.text
    assert "ghp_never_echoed" not in response.text
    (row,) = await _rows(pg_session_factory, org.id)
    expected = (app_settings.storage.repos_dir / org.slug / "widgets").resolve()
    assert row.path == str(expected)
    assert (row.main_branch, row.develop_branch) == ("trunk", "develop")


async def test_a_failed_clone_is_a_400_and_registers_nothing(
    client: AsyncClient, pg_session_factory: Factory, root: Path
) -> None:
    org = await make_org(pg_session_factory)
    response = await client.post(
        f"{REPOS}/clone", headers=org.owner.headers, json={"url": "https://gitlab.com/a/b"}
    )
    assert response.status_code == 400
    assert "Only GitHub URLs" in response.json()["detail"]
    assert await _rows(pg_session_factory, org.id) == []
