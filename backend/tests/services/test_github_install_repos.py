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

"""Tests for the bulk-import service layer.

These run the GitHub-API client through ``respx`` (no real network) and
stub out the DB-touching repository so the tests don't need a Postgres
fixture. The full HTTP+DB integration harness doesn't exist in this
repo (see ``tests/api/v1/test_settings_connections_status.py`` for the
historical reason); the equivalent route-level tests for the new
endpoints will land in a separate phase that introduces the harness.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import respx
from httpx import Response

from app.schemas.repo_install import AppInstallState
from app.services import github_install_repos
from app.services.github_install_repos import (
    GITHUB_BASE_URL,
    INSTALLATION_REPOS_PATH,
    REPO_BRANCHES_PATH_TEMPLATE,
    compose_app_clone_url,
    list_installation_repos,
    list_remote_branches_via_api,
    resolve_app_install_state,
)


class _FakeOrg:
    """Stand-in for ``Organization`` — only the GitHub-App columns are read."""

    def __init__(
        self,
        *,
        app_id: int | None = 12345,
        private_key: str | None = "encrypted-pem",
        installation_id: int | None = 999,
        slug: str | None = "acme-bodhi",
    ) -> None:
        self.id: uuid.UUID = uuid.uuid4()
        self.github_app_id = app_id
        self.github_app_private_key = private_key
        self.github_app_installation_id = installation_id
        self.github_app_slug = slug


class _FakeRepoRepo:
    """Stand-in for ``TrackedRepoRepository.get_full_names_by_org``.

    Records construction so tests can assert it was scoped to the org.
    """

    def __init__(
        self,
        _db: Any,
        *,
        org_id: uuid.UUID | None = None,
        full_names: set[str] | None = None,
    ) -> None:
        self._org_id = org_id
        self._full_names = full_names or set()

    async def get_full_names_by_org(self) -> set[str]:
        return set(self._full_names)


@pytest.fixture(autouse=True)
def _patch_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the App-token fetch with a static stub for these tests.

    The token-exchange path is covered by ``test_github_app_auth.py``;
    here we only care about how the service uses the token, not how it
    obtains one.
    """

    async def _fake_token(_org: Any) -> str | None:
        return "ghs_test_token_xxx"

    monkeypatch.setattr(github_install_repos, "get_installation_token", _fake_token)


def test_compose_app_clone_url() -> None:
    """The clone URL must embed the token via ``x-access-token``."""
    url = compose_app_clone_url("ghs_abc", "acme/widgets")
    assert url == "https://x-access-token:ghs_abc@github.com/acme/widgets.git"


def test_resolve_app_install_state_no_credentials() -> None:
    """Missing app_id or private key short-circuits to ``NO_CREDENTIALS``."""
    org = _FakeOrg(app_id=None)
    state, install_url = resolve_app_install_state(org)  # type: ignore[arg-type]
    assert state is AppInstallState.NO_CREDENTIALS
    assert install_url is None


def test_resolve_app_install_state_no_install() -> None:
    """Creds present, install_id absent → ``NO_INSTALL`` + install URL."""
    org = _FakeOrg(installation_id=None)
    state, install_url = resolve_app_install_state(org)  # type: ignore[arg-type]
    assert state is AppInstallState.NO_INSTALL
    assert install_url == "https://github.com/apps/acme-bodhi/installations/new"


def test_resolve_app_install_state_ready() -> None:
    """Fully configured org → ``READY``. Install URL still useful for re-install."""
    org = _FakeOrg()
    state, install_url = resolve_app_install_state(org)  # type: ignore[arg-type]
    assert state is AppInstallState.READY
    assert install_url == "https://github.com/apps/acme-bodhi/installations/new"


def test_resolve_app_install_state_no_install_no_slug() -> None:
    """Without a slug we can't build the install URL — return ``None``."""
    org = _FakeOrg(installation_id=None, slug=None)
    state, install_url = resolve_app_install_state(org)  # type: ignore[arg-type]
    assert state is AppInstallState.NO_INSTALL
    assert install_url is None


@pytest.mark.asyncio
@respx.mock
async def test_list_installation_repos_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two-page response yields all repos; ``already_tracked`` joins correctly."""
    org = _FakeOrg()
    page1 = {
        "total_count": 3,
        "repositories": [
            _gh_repo("acme/one"),
            _gh_repo("acme/two"),
        ],
    }
    page2 = {
        "total_count": 3,
        "repositories": [_gh_repo("acme/three")],
    }
    next_url = f"{GITHUB_BASE_URL}{INSTALLATION_REPOS_PATH}?page=2&per_page=100"
    route = respx.get(f"{GITHUB_BASE_URL}{INSTALLATION_REPOS_PATH}").mock(
        side_effect=[
            Response(
                200,
                json=page1,
                headers={"link": f'<{next_url}>; rel="next"'},
            ),
            Response(200, json=page2),
        ]
    )

    monkeypatch.setattr(
        github_install_repos,
        "TrackedRepoRepository",
        lambda db, org_id=None: _FakeRepoRepo(db, org_id=org_id, full_names={"acme/two"}),
    )

    repos = await list_installation_repos(org, db=object())  # type: ignore[arg-type]

    assert [r.full_name for r in repos] == ["acme/one", "acme/two", "acme/three"]
    flags = {r.full_name: r.already_tracked for r in repos}
    assert flags == {"acme/one": False, "acme/two": True, "acme/three": False}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_list_installation_repos_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No token → empty list (caller handles the install CTA)."""

    async def _no_token(_org: Any) -> str | None:
        return None

    monkeypatch.setattr(github_install_repos, "get_installation_token", _no_token)
    repos = await list_installation_repos(_FakeOrg(), db=object())  # type: ignore[arg-type]
    assert repos == []


@pytest.mark.asyncio
@respx.mock
async def test_list_remote_branches_via_api_pagination() -> None:
    """Branches paginate the same way installation repos do."""
    org = _FakeOrg()
    full_name = "acme/widgets"
    path = REPO_BRANCHES_PATH_TEMPLATE.format(full_name=full_name)
    next_url = f"{GITHUB_BASE_URL}{path}?page=2&per_page=100"
    respx.get(f"{GITHUB_BASE_URL}{path}").mock(
        side_effect=[
            Response(
                200,
                json=[{"name": "main"}, {"name": "develop"}],
                headers={"link": f'<{next_url}>; rel="next"'},
            ),
            Response(200, json=[{"name": "release/2026-q2"}]),
        ]
    )

    branches = await list_remote_branches_via_api(org, full_name)  # type: ignore[arg-type]
    assert branches == ["main", "develop", "release/2026-q2"]


def _gh_repo(full_name: str) -> dict[str, Any]:
    """Synthetic GitHub repository payload — only the fields we read."""
    owner, _, name = full_name.partition("/")
    return {
        "id": abs(hash(full_name)) % (10**9),
        "full_name": full_name,
        "name": name,
        "private": True,
        "default_branch": "main",
        "pushed_at": "2026-04-29T15:32:11Z",
        "owner": {
            "login": owner,
            "avatar_url": f"https://github.com/{owner}.png",
        },
    }
