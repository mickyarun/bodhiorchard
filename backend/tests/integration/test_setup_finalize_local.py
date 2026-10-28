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

"""Stage two of the wizard, local paths, end to end on Postgres.

The path guards themselves are pinned with stubs in
``tests/api/v1/test_setup_finalize_paths.py``; this checks what lands in
``tracked_repositories`` for real checkouts, and that a re-run updates
rather than duplicates. The scan kickoff is recorded, never started.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.services import setup_finalize_legacy as legacy
from tests.api.v1.repo_path_support import init_repo
from tests.integration.settings_support import Factory, make_org

pytestmark = pytest.mark.integration

FINALIZE = "/api/setup/finalize-with-repos"


@pytest.fixture
def root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = (tmp_path / "home").resolve()
    path.mkdir()
    monkeypatch.setattr(legacy, "picker_roots", lambda: (path,))
    return path


@pytest.fixture
def kicked(monkeypatch: pytest.MonkeyPatch) -> list[list[uuid.UUID]]:
    batches: list[list[uuid.UUID]] = []

    async def _kick(
        *, org_id: uuid.UUID, repo_ids: list[uuid.UUID]
    ) -> tuple[uuid.UUID | None, None]:
        # Like the real kickoff: an empty batch starts nothing.
        batches.append(list(repo_ids))
        return (uuid.uuid4() if repo_ids else None), None

    monkeypatch.setattr(legacy, "kick_off_onboard_scan", _kick)
    return batches


def _body(*repos: dict[str, str]) -> dict[str, object]:
    return {"sourceCode": {"repos": list(repos)}}


async def _rows(factory: Factory, org_id: uuid.UUID) -> list[TrackedRepository]:
    async with factory() as db:
        result = await db.scalars(
            select(TrackedRepository)
            .where(TrackedRepository.org_id == org_id)
            .order_by(TrackedRepository.name)
        )
        return list(result)


async def test_registers_checkouts_with_their_branches_and_skips_the_rest(
    client: AsyncClient,
    pg_session_factory: Factory,
    root: Path,
    kicked: list[list[uuid.UUID]],
) -> None:
    org = await make_org(pg_session_factory)
    api = init_repo(root / "api", "develop")
    web = init_repo(root / "web")
    (root / "plain").mkdir()

    response = await client.post(
        FINALIZE,
        headers=org.owner.headers,
        json=_body(
            {"path": str(api), "mainBranch": "main", "developBranch": "develop"},
            {"path": str(web)},
            {"path": str(root / "plain")},
            {"path": str(root / "missing")},
            {"path": "/etc"},
        ),
    )

    assert response.status_code == 201, response.text
    assert response.json()["isSetupComplete"] is True
    rows = await _rows(pg_session_factory, org.id)
    assert [(r.name, r.path, r.status) for r in rows] == [
        ("api", str(api), RepoStatus.ACTIVE),
        ("web", str(web), RepoStatus.ACTIVE),
    ]
    assert (rows[0].main_branch, rows[0].develop_branch) == ("main", "develop")
    assert sorted(kicked[0]) == sorted(r.id for r in rows)


async def test_a_rerun_reuses_the_row_and_updates_its_branches(
    client: AsyncClient,
    pg_session_factory: Factory,
    root: Path,
    kicked: list[list[uuid.UUID]],
) -> None:
    org = await make_org(pg_session_factory)
    repo = init_repo(root / "svc", "dev")
    first = _body({"path": str(repo), "mainBranch": "main"})
    second = _body({"path": f"{root}/../home/svc", "mainBranch": "main", "developBranch": "dev"})

    for body in (first, second):
        response = await client.post(FINALIZE, headers=org.owner.headers, json=body)
        assert response.status_code == 201, response.text

    rows = await _rows(pg_session_factory, org.id)
    assert len(rows) == 1
    assert (rows[0].path, rows[0].develop_branch) == (str(repo), "dev")
    assert kicked == [[rows[0].id], [rows[0].id]]


async def test_nothing_usable_registers_nothing_and_starts_no_scan(
    client: AsyncClient,
    pg_session_factory: Factory,
    root: Path,
    kicked: list[list[uuid.UUID]],
) -> None:
    org = await make_org(pg_session_factory)
    response = await client.post(
        FINALIZE, headers=org.owner.headers, json=_body({"path": str(root / "missing")})
    )
    assert response.status_code == 201
    assert response.json()["scanId"] is None
    assert await _rows(pg_session_factory, org.id) == []
    assert kicked == [[]]


async def test_a_developer_cannot_finalize(
    client: AsyncClient,
    pg_session_factory: Factory,
    root: Path,
    kicked: list[list[uuid.UUID]],
) -> None:
    org = await make_org(pg_session_factory)
    repo = init_repo(root / "svc")
    response = await client.post(
        FINALIZE, headers=org.developer.headers, json=_body({"path": str(repo)})
    )
    assert response.status_code == 403
    assert await _rows(pg_session_factory, org.id) == []
    assert kicked == []


async def test_the_same_path_in_two_orgs_is_two_independent_rows(
    client: AsyncClient,
    pg_session_factory: Factory,
    root: Path,
    kicked: list[list[uuid.UUID]],
) -> None:
    one, two = await make_org(pg_session_factory), await make_org(pg_session_factory)
    repo = init_repo(root / "shared")
    for org, branch in ((one, "main"), (two, "trunk")):
        body = _body({"path": str(repo), "mainBranch": branch})
        response = await client.post(FINALIZE, headers=org.owner.headers, json=body)
        assert response.status_code == 201

    (row_one,) = await _rows(pg_session_factory, one.id)
    (row_two,) = await _rows(pg_session_factory, two.id)
    assert row_one.id != row_two.id
    assert (row_one.main_branch, row_two.main_branch) == ("main", "trunk")
