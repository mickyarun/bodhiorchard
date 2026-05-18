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

"""Tests for ``refresh_origin_auth`` — the scan-ingest auth-refresh helper.

Exercises each branch of the decision tree (no origin / SSH / HTTPS+App
ready / HTTPS+no org / HTTPS+app not ready / HTTPS+token-mint failure /
HTTPS+non-github host) without needing a real git repo or DB session.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest

from app.models.organization import Organization
from app.schemas.repo_install import AppInstallState
from app.services.scan.stages import _origin_auth as mod


class _FakeOrg:
    """Minimal stand-in for ``Organization`` — only the attrs we touch."""

    def __init__(self, *, app_ready: bool = True) -> None:
        self.id = uuid.uuid4()
        self._app_ready = app_ready


def _as_org(fake: _FakeOrg) -> Organization:
    """Duck-type a ``_FakeOrg`` as an ``Organization`` for the helper signature.

    The helper only reads ``org.id`` and what the patched
    ``resolve_app_install_state`` / ``get_installation_token`` return —
    none of which actually touch the SQLAlchemy ORM.
    """
    return cast(Organization, fake)


def _patch_run_git(
    monkeypatch: pytest.MonkeyPatch,
    *,
    origin_url: str | None,
    set_url_rc: int = 0,
) -> list[list[str]]:
    """Stub ``run_git`` so the helper sees the desired origin and records writes."""
    invocations: list[list[str]] = []

    async def fake(args: list[str], cwd: str, **_kw: Any) -> tuple[str, str, int]:
        invocations.append(args)
        if args[:3] == ["remote", "get-url", "origin"]:
            if origin_url is None:
                return ("", "fatal: No such remote 'origin'", 1)
            return (origin_url, "", 0)
        if args[:3] == ["remote", "set-url", "origin"]:
            return ("", "" if set_url_rc == 0 else "boom", set_url_rc)
        return ("", "", 0)

    monkeypatch.setattr(mod, "run_git", fake)
    return invocations


def _patch_app_state(
    monkeypatch: pytest.MonkeyPatch,
    state: AppInstallState,
) -> None:
    monkeypatch.setattr(
        mod,
        "resolve_app_install_state",
        lambda _org: (state, None),
    )


def _patch_token(monkeypatch: pytest.MonkeyPatch, token: str | None) -> None:
    async def fake(_org: Any) -> str | None:
        return token

    monkeypatch.setattr(mod, "get_installation_token", fake)


def _patch_ssh_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    monkeypatch.setattr(mod, "ssh_env", lambda: env)


async def test_no_origin_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_git(monkeypatch, origin_url=None)
    result = await mod.refresh_origin_auth("/repo", _as_org(_FakeOrg()))
    assert result is None


async def test_ssh_origin_returns_ssh_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_git(monkeypatch, origin_url="git@github.com:owner/repo.git")
    sentinel_env = {"GIT_SSH_COMMAND": "ssh -i /tmp/key"}
    _patch_ssh_env(monkeypatch, sentinel_env)
    result = await mod.refresh_origin_auth("/repo", _as_org(_FakeOrg()))
    assert result is sentinel_env


async def test_ssh_origin_does_not_need_org(monkeypatch: pytest.MonkeyPatch) -> None:
    """SSH path bypasses org lookup entirely."""
    _patch_run_git(monkeypatch, origin_url="ssh://git@github.com/owner/repo.git")
    _patch_ssh_env(monkeypatch, {"GIT_SSH_COMMAND": "ssh"})
    result = await mod.refresh_origin_auth("/repo", None)
    assert result == {"GIT_SSH_COMMAND": "ssh"}


async def test_https_no_org_leaves_url_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    invocations = _patch_run_git(
        monkeypatch,
        origin_url="https://github.com/owner/repo.git",
    )
    result = await mod.refresh_origin_auth("/repo", None)
    assert result is None
    assert not any(call[:3] == ["remote", "set-url", "origin"] for call in invocations)


async def test_https_app_not_ready_leaves_url_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    invocations = _patch_run_git(
        monkeypatch,
        origin_url="https://github.com/owner/repo.git",
    )
    _patch_app_state(monkeypatch, AppInstallState.NO_INSTALL)
    result = await mod.refresh_origin_auth("/repo", _as_org(_FakeOrg(app_ready=False)))
    assert result is None
    assert not any(call[:3] == ["remote", "set-url", "origin"] for call in invocations)


async def test_https_token_unavailable_leaves_url_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocations = _patch_run_git(
        monkeypatch,
        origin_url="https://github.com/owner/repo.git",
    )
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, None)
    result = await mod.refresh_origin_auth("/repo", _as_org(_FakeOrg()))
    assert result is None
    assert not any(call[:3] == ["remote", "set-url", "origin"] for call in invocations)


async def test_https_app_ready_rewrites_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    invocations = _patch_run_git(
        monkeypatch,
        origin_url="https://github.com/owner/repo.git",
    )
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, "ghs_FAKE_TOKEN")

    result = await mod.refresh_origin_auth("/repo", _as_org(_FakeOrg()))

    assert result is None
    set_url_calls = [call for call in invocations if call[:3] == ["remote", "set-url", "origin"]]
    assert len(set_url_calls) == 1
    new_url = set_url_calls[0][3]
    assert new_url == "https://x-access-token:ghs_FAKE_TOKEN@github.com/owner/repo.git"


async def test_https_app_ready_with_existing_creds_in_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prior token baked into origin doesn't confuse owner/repo extraction."""
    invocations = _patch_run_git(
        monkeypatch,
        origin_url="https://x-access-token:OLD_TOKEN@github.com/owner/repo.git",
    )
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, "ghs_NEW")

    await mod.refresh_origin_auth("/repo", _as_org(_FakeOrg()))

    set_url_calls = [call for call in invocations if call[:3] == ["remote", "set-url", "origin"]]
    assert len(set_url_calls) == 1
    assert set_url_calls[0][3] == "https://x-access-token:ghs_NEW@github.com/owner/repo.git"


async def test_https_non_github_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-github HTTPS hosts must NOT have their origin rewritten."""
    invocations = _patch_run_git(
        monkeypatch,
        origin_url="https://gitlab.com/owner/repo.git",
    )
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, "ghs_FAKE")

    result = await mod.refresh_origin_auth("/repo", _as_org(_FakeOrg()))

    assert result is None
    assert not any(call[:3] == ["remote", "set-url", "origin"] for call in invocations)


async def test_set_url_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed `git remote set-url` is logged but doesn't blow up the caller."""
    _patch_run_git(
        monkeypatch,
        origin_url="https://github.com/owner/repo.git",
        set_url_rc=1,
    )
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, "ghs_FAKE")
    result = await mod.refresh_origin_auth("/repo", _as_org(_FakeOrg()))
    assert result is None


# ---- build_app_https_url_for_origin ---------------------------------


async def test_app_fallback_ssh_origin_returns_https_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSH origin + READY App + token → composed HTTPS URL."""
    _patch_run_git(monkeypatch, origin_url="git@github.com:owner/repo.git")
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, "ghs_FALLBACK")

    url = await mod.build_app_https_url_for_origin("/repo", _as_org(_FakeOrg()))

    assert url == "https://x-access-token:ghs_FALLBACK@github.com/owner/repo.git"


async def test_app_fallback_ssh_scheme_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ssh://git@github.com/owner/repo.git`` parses too."""
    _patch_run_git(monkeypatch, origin_url="ssh://git@github.com/owner/repo.git")
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, "ghs_T")

    url = await mod.build_app_https_url_for_origin("/repo", _as_org(_FakeOrg()))

    assert url == "https://x-access-token:ghs_T@github.com/owner/repo.git"


async def test_app_fallback_https_origin_returns_https_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_run_git(monkeypatch, origin_url="https://github.com/owner/repo.git")
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, "ghs_T")

    url = await mod.build_app_https_url_for_origin("/repo", _as_org(_FakeOrg()))

    assert url == "https://x-access-token:ghs_T@github.com/owner/repo.git"


async def test_app_fallback_no_origin_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_git(monkeypatch, origin_url=None)
    url = await mod.build_app_https_url_for_origin("/repo", _as_org(_FakeOrg()))
    assert url is None


async def test_app_fallback_no_org_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_git(monkeypatch, origin_url="git@github.com:owner/repo.git")
    url = await mod.build_app_https_url_for_origin("/repo", None)
    assert url is None


async def test_app_fallback_app_not_ready_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_run_git(monkeypatch, origin_url="git@github.com:owner/repo.git")
    _patch_app_state(monkeypatch, AppInstallState.NO_INSTALL)
    url = await mod.build_app_https_url_for_origin("/repo", _as_org(_FakeOrg()))
    assert url is None


async def test_app_fallback_token_unavailable_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_run_git(monkeypatch, origin_url="git@github.com:owner/repo.git")
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, None)
    url = await mod.build_app_https_url_for_origin("/repo", _as_org(_FakeOrg()))
    assert url is None


async def test_app_fallback_non_github_ssh_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSH URL whose host isn't github.com — we don't rewrite arbitrary remotes."""
    _patch_run_git(monkeypatch, origin_url="git@gitlab.com:owner/repo.git")
    _patch_app_state(monkeypatch, AppInstallState.READY)
    _patch_token(monkeypatch, "ghs_T")
    url = await mod.build_app_https_url_for_origin("/repo", _as_org(_FakeOrg()))
    assert url is None
