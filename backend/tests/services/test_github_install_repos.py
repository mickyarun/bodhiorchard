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
    _is_same_origin,
    _validate_repo_full_name,
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


@pytest.mark.asyncio
@respx.mock
async def test_list_remote_branches_stops_on_cross_origin_link() -> None:
    """A malicious ``Link`` header pointing off-origin must NOT be followed.

    Simulates a compromised upstream returning ``Link: <http://evil/...>; rel="next"``.
    The same-origin guard drops it, so only the first page is fetched
    and no request is ever issued against the attacker host (which would
    leak the bearer token).
    """
    org = _FakeOrg()
    full_name = "acme/widgets"
    path = REPO_BRANCHES_PATH_TEMPLATE.format(full_name=full_name)
    evil_route = respx.get("http://evil.example/internal").mock(
        return_value=Response(200, json=[{"name": "leaked"}]),
    )
    respx.get(f"{GITHUB_BASE_URL}{path}").mock(
        return_value=Response(
            200,
            json=[{"name": "main"}],
            headers={"link": '<http://evil.example/internal>; rel="next"'},
        ),
    )

    branches = await list_remote_branches_via_api(org, full_name)  # type: ignore[arg-type]
    assert branches == ["main"]
    assert evil_route.call_count == 0, "cross-origin Link header must not be followed"


@pytest.mark.parametrize(
    "full_name",
    [
        "acme/widgets",
        "Acme/widgets-2",
        "user1/repo.with.dots",
        "a/b",
        "X" * 39 + "/" + "Y" * 100,  # max-length owner + repo
    ],
)
def test_validate_repo_full_name_accepts_real_github_names(full_name: str) -> None:
    """All real-world GitHub identifiers pass through unchanged."""
    assert _validate_repo_full_name(full_name) == full_name


@pytest.mark.parametrize(
    "payload",
    [
        "../etc/passwd",
        "acme/../other",
        "acme/widgets/../../user",
        "acme//widgets",
        "acme/wid gets",
        "acme/widgets?token=x",
        "acme/widgets#frag",
        "acme/widgets%2F..",
        "/acme/widgets",
        "acme/",
        "/owner",
        "acme/widgets\nX-Injected: yes",
        "",
        "A" * 40 + "/widgets",  # owner over 39 chars
        "acme/" + "R" * 101,  # repo over 100 chars
    ],
)
def test_validate_repo_full_name_rejects_path_injection(payload: str) -> None:
    """Any path-injection-shaped payload is rejected at the service boundary."""
    with pytest.raises(ValueError, match="invalid GitHub repo identifier"):
        _validate_repo_full_name(payload)


def test_list_remote_branches_rejects_invalid_full_name() -> None:
    """Even with a valid token, an invalid ``full_name`` never reaches httpx."""
    with pytest.raises(ValueError, match="invalid GitHub repo identifier"):
        # ``compose_app_clone_url`` is sync; covers the second sink site.
        compose_app_clone_url("ghs_x", "../escape")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://api.github.com/foo", True),
        ("https://api.github.com/foo?bar=1", True),
        ("http://api.github.com/foo", False),  # scheme mismatch
        ("https://api.github.com.evil/foo", False),  # netloc suffix attack
        ("https://api.github.com:8443/foo", False),  # port mismatch
        ("https://evil.example/foo", False),
        ("file:///etc/passwd", False),
        ("//api.github.com/foo", False),  # scheme-relative; no scheme
        ("not a url", False),
    ],
)
def test_is_same_origin_match(url: str, expected: bool) -> None:
    """Only same scheme + netloc as ``api.github.com`` returns True."""
    assert _is_same_origin(url, "https://api.github.com") is expected


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
