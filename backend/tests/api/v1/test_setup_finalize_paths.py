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

"""The wizard's finalize registers local paths on the same terms as add-by-path.

``POST /api/setup/finalize-with-repos`` with a ``sourceCode`` payload
upserts each caller-chosen path as a tracked repo and scans it, so it
carries the guards of ``POST /api/v1/settings/repos``
(``test_settings_repos_add.py``):

* **by caller**: a session plus ``settings:edit`` — no token is a 401, a
  member without the permission a 403.
* **in space**: the resolved path must sit under a ``picker_roots`` root
  and outside the shared clone root — except the org's own clone folder,
  where the wizard's GitHub-clone tab puts the repos it lists here. A path
  that fails is skipped, like any other unusable entry in the batch.

Requests go through a real ASGI app so the route dependency runs; the
user and permission lookups are stubbed, and so are the repositories and
the scan kickoff, since the repo has no HTTP+DB fixture (see
``tests/conftest.py``).
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from structlog.testing import capture_logs

from app.api.v1 import setup as setup_api
from app.config import settings as app_settings
from app.core.auth_deps import get_current_user, get_db
from app.core.permission_deps import PermissionSet, get_permission_set
from app.services import setup_finalize_legacy as legacy

FINALIZE = "/api/setup/finalize-with-repos"
ORG_SLUG = "acme"


class _Session:
    """Just enough of an ``AsyncSession`` for the legacy arm's flush + commit."""

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


class _Orgs:
    def __init__(self, _db: object) -> None:
        pass

    async def get_for_user(self, _user: object) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), slug=ORG_SLUG)


class _TrackedRepos:
    """Records what the legacy arm registers, so tests can assert on it."""

    registered: list[str] = []

    def __init__(self, _db: object, *, org_id: uuid.UUID) -> None:
        pass

    async def upsert(self, path: str, _name: str) -> SimpleNamespace:
        _TrackedRepos.registered.append(path)
        return SimpleNamespace(id=uuid.uuid4(), main_branch=None, develop_branch=None)


async def _session() -> AsyncIterator[_Session]:
    yield _Session()


def _app(permissions: frozenset[str] | None) -> FastAPI:
    """The router at its production prefix; ``None`` means no session."""
    app = FastAPI()
    app.include_router(setup_api.router, prefix="/api/setup")
    app.dependency_overrides[get_db] = _session
    if permissions is not None:
        user = SimpleNamespace(id=uuid.uuid4(), must_change_password=False)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_permission_set] = lambda: PermissionSet(
            ids=permissions, is_owner=False
        )
    return app


@pytest.fixture(autouse=True)
def stub_repositories(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    _TrackedRepos.registered = []
    monkeypatch.setattr(setup_api, "OrganizationRepository", _Orgs)
    monkeypatch.setattr(legacy, "TrackedRepoRepository", _TrackedRepos)
    yield _TrackedRepos.registered


@pytest.fixture(autouse=True)
def scanned(monkeypatch: pytest.MonkeyPatch) -> list[list[uuid.UUID]]:
    """Repo-id batches handed to the scan kickoff — no real scan runs."""
    batches: list[list[uuid.UUID]] = []

    async def _kick_off(*, org_id: uuid.UUID, repo_ids: list[uuid.UUID]) -> tuple[uuid.UUID, None]:
        batches.append(repo_ids)
        return uuid.uuid4(), None

    monkeypatch.setattr(legacy, "kick_off_onboard_scan", _kick_off)
    return batches


@pytest.fixture
async def anonymous() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=_app(None)), base_url="http://t") as c:
        yield c


@pytest.fixture
async def viewer() -> AsyncIterator[AsyncClient]:
    """Signed in, but only ``settings:view`` — like the developer and QA roles."""
    app = _app(frozenset({"settings:view"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.fixture
async def editor() -> AsyncIterator[AsyncClient]:
    app = _app(frozenset({"settings:view", "settings:edit"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.fixture
def picker_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the allowed root at a temp directory, not the real home."""
    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(legacy, "picker_roots", lambda: (root,))
    return root


@pytest.fixture
def host_clone_root(monkeypatch: pytest.MonkeyPatch, picker_root: Path) -> Path:
    """A host install's clone root: ``<repo-root>/repoclone``, so under home."""
    data_dir = picker_root / "code" / "bodhiorchard" / "repoclone"
    monkeypatch.setattr(app_settings.storage, "data_dir", str(data_dir))
    return app_settings.storage.repos_dir


def _checkout(parent: Path, name: str) -> Path:
    repo = parent / name
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    return repo


def _body(*paths: Path | str) -> dict[str, object]:
    return {"sourceCode": {"repos": [{"path": str(p), "mainBranch": "main"} for p in paths]}}


class TestNeedsAnEditorSession:
    """The caller guard: runs before anything touches the filesystem."""

    async def test_no_token_is_401(
        self, anonymous: AsyncClient, picker_root: Path, stub_repositories: list[str]
    ) -> None:
        repo = _checkout(picker_root, "taskflow")
        response = await anonymous.post(FINALIZE, json=_body(repo))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert stub_repositories == []

    async def test_without_settings_edit_is_403(
        self,
        viewer: AsyncClient,
        picker_root: Path,
        stub_repositories: list[str],
        scanned: list[list[uuid.UUID]],
    ) -> None:
        repo = _checkout(picker_root, "taskflow")
        response = await viewer.post(FINALIZE, json=_body(repo))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert stub_repositories == []
        assert scanned == []


class TestConfinedToTheRoots:
    """The space guard: a path outside the allowed roots is never registered."""

    async def test_skips_a_checkout_outside(
        self,
        editor: AsyncClient,
        picker_root: Path,
        tmp_path: Path,
        stub_repositories: list[str],
        scanned: list[list[uuid.UUID]],
    ) -> None:
        outside = _checkout(tmp_path, "elsewhere")
        response = await editor.post(FINALIZE, json=_body(outside))
        assert response.status_code == status.HTTP_201_CREATED
        assert stub_repositories == []
        assert scanned == [[]]

    async def test_skips_traversal_and_symlink_escapes(
        self, editor: AsyncClient, picker_root: Path, tmp_path: Path, stub_repositories: list[str]
    ) -> None:
        """realpath collapses ``..`` and follows links before the check."""
        outside = _checkout(tmp_path, "elsewhere")
        (picker_root / "escape").symlink_to(outside)
        response = await editor.post(
            FINALIZE, json=_body(f"{picker_root}/../elsewhere", picker_root / "escape")
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert stub_repositories == []

    async def test_skips_another_orgs_clone_under_a_root(
        self, editor: AsyncClient, host_clone_root: Path, stub_repositories: list[str]
    ) -> None:
        """The clone root holds every org's clones side by side.

        On a host install it sits under home, so the roots check alone
        would let one org register another's clone.
        """
        cloned = _checkout(host_clone_root / "other-org", "billing")

        response = await editor.post(FINALIZE, json=_body(cloned))

        assert response.status_code == status.HTTP_201_CREATED
        assert stub_repositories == []

    async def test_skips_a_case_variant_of_the_clone_root(
        self, editor: AsyncClient, host_clone_root: Path, stub_repositories: list[str]
    ) -> None:
        """realpath keeps the typed case; macOS volumes still open the path.

        Asserts the clone-root deny fired, not just that nothing registered:
        on a case-sensitive disk the variant doesn't exist, so without this
        the test would pass through the "invalid repo" skip instead.
        """
        cloned = _checkout(host_clone_root / "other-org", "billing")
        variant = str(cloned).replace("/repoclone/", "/REPOCLONE/")

        with capture_logs() as logs:
            response = await editor.post(FINALIZE, json=_body(variant))

        assert response.status_code == status.HTTP_201_CREATED
        assert stub_repositories == []
        assert any(e["event"] == "setup_skip_repo_outside_roots" for e in logs)


class TestStillRegistersWhatTheWizardSends:
    """Neither guard may break the entries the wizard itself produces."""

    async def test_registers_a_checkout_under_a_root(
        self,
        editor: AsyncClient,
        picker_root: Path,
        tmp_path: Path,
        stub_repositories: list[str],
        scanned: list[list[uuid.UUID]],
    ) -> None:
        """A refused entry is skipped; the rest of the batch still lands."""
        repo = _checkout(picker_root, "taskflow")
        outside = _checkout(tmp_path, "elsewhere")

        response = await editor.post(FINALIZE, json=_body(outside, repo))

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["scanId"] is not None
        assert stub_repositories == [str(repo.resolve())]
        assert len(scanned) == 1
        assert len(scanned[0]) == 1

    async def test_registers_the_orgs_own_clone_under_a_root(
        self, editor: AsyncClient, host_clone_root: Path, stub_repositories: list[str]
    ) -> None:
        """A host install's clones sit under both home and the clone root."""
        cloned = _checkout(host_clone_root / ORG_SLUG, "billing")

        response = await editor.post(FINALIZE, json=_body(cloned))

        assert response.status_code == status.HTTP_201_CREATED
        assert stub_repositories == [str(cloned.resolve())]

    async def test_registers_the_orgs_own_clone_outside_the_roots(
        self,
        editor: AsyncClient,
        picker_root: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        stub_repositories: list[str],
    ) -> None:
        """Docker keeps clones in ``/data/repos``, outside home.

        The wizard's GitHub-clone tab lists them in ``sourceCode`` to get
        them scanned, so the org's own clone folder is accepted.
        """
        monkeypatch.setattr(app_settings.storage, "data_dir", str(tmp_path / "data"))
        cloned = _checkout(app_settings.storage.repos_dir / ORG_SLUG, "billing")

        response = await editor.post(FINALIZE, json=_body(cloned))

        assert response.status_code == status.HTTP_201_CREATED
        assert stub_repositories == [str(cloned.resolve())]
