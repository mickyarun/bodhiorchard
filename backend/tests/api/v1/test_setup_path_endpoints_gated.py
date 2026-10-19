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

"""The two path-taking setup endpoints must close when setup completes.

``browse_directories`` and ``get_repo_branches`` are unauthenticated — the
wizard needs a directory picker before an org or a JWT exists. Both take a
caller-chosen filesystem path, so left open after setup they are a
filesystem walker and a filesystem prober for anyone who can reach the
port. Every other pre-auth endpoint in that router already calls
``_require_setup_incomplete``; these two did not, and CodeQL flagged them
as ``py/path-injection``.

A guard with no test is a guard that gets deleted, so these assert both
halves: closed once an org exists, and still working while setup is open.

Same harness style as ``test_setup_two_stage.py`` — the handlers are called
directly with the organization lookup stubbed, since the repo has no
HTTP+DB fixture (see ``tests/conftest.py``).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException, status

from app.api.v1 import setup as setup_api


class _OrgRepoStub:
    """Stands in for ``OrganizationRepository``; only the guard's call."""

    setup_exists: Any = None

    def __init__(self, _db: Any) -> None:
        pass

    async def check_setup_exists(self) -> Any:
        return type(self).setup_exists


@pytest.fixture
def setup_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the guard see an existing organization."""
    _OrgRepoStub.setup_exists = object()
    monkeypatch.setattr(setup_api, "OrganizationRepository", _OrgRepoStub)


@pytest.fixture
def setup_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the guard see a fresh install with no organization yet."""
    _OrgRepoStub.setup_exists = None
    monkeypatch.setattr(setup_api, "OrganizationRepository", _OrgRepoStub)


async def test_browse_directories_is_closed_once_setup_completes(
    setup_complete: None, tmp_path: Any
) -> None:
    with pytest.raises(HTTPException) as caught:
        await setup_api.browse_directories(path=str(tmp_path), db=None)  # type: ignore[arg-type]
    assert caught.value.status_code == status.HTTP_403_FORBIDDEN


async def test_repo_branches_is_closed_once_setup_completes(
    setup_complete: None, tmp_path: Any
) -> None:
    with pytest.raises(HTTPException) as caught:
        await setup_api.get_repo_branches(path=str(tmp_path), db=None)  # type: ignore[arg-type]
    assert caught.value.status_code == status.HTTP_403_FORBIDDEN


async def test_browse_directories_still_serves_the_wizard(setup_open: None, tmp_path: Any) -> None:
    """The gate must not break the case it exists to allow."""
    (tmp_path / "repos").mkdir()
    (tmp_path / "notes.txt").write_text("not a directory")

    result = await setup_api.browse_directories(path=str(tmp_path), db=None)  # type: ignore[arg-type]

    assert result.current_path == str(tmp_path)
    assert [entry.name for entry in result.directories] == ["repos"]
