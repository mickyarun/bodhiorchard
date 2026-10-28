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

"""Bulk onboarding without the network: clones served from local bare repos.

The job clones ``https://x-access-token:<token>@github.com/<owner>/<repo>.git``.
:class:`CloneRedirects` points exactly that URL at a local bare repository
through git's own ``url.<base>.insteadOf`` rewrite, passed in the
``GIT_CONFIG_COUNT`` environment the app's ``git`` subprocess inherits, so
the real ``clone_or_update`` runs unchanged. A URL with no redirect still
fails, because the guard only lets git speak the ``file`` protocol.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

from app.services import job_repo_bulk_clone
from tests.fakes.git_repo import LocalGitRepo


class CloneRedirects:
    """Serve chosen authenticated GitHub clone URLs from local bare repos."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._count = 0

    def serve(self, token: str, full_name: str, repo: LocalGitRepo) -> None:
        """Clone ``full_name`` (with ``token``) from ``repo``'s bare origin."""
        url = f"https://x-access-token:{token}@github.com/{full_name}.git"
        index = self._count
        self._monkeypatch.setenv(f"GIT_CONFIG_KEY_{index}", f"url.file://{repo.origin}.insteadOf")
        self._monkeypatch.setenv(f"GIT_CONFIG_VALUE_{index}", url)
        self._count += 1
        self._monkeypatch.setenv("GIT_CONFIG_COUNT", str(self._count))


@dataclass
class ScanKickoffs:
    """Stands in for the onboarding scan; records which repos it was given."""

    calls: list[list[uuid.UUID]] = field(default_factory=list)
    warning: str | None = None

    async def __call__(
        self, *, org_id: uuid.UUID, repo_ids: list[uuid.UUID]
    ) -> tuple[uuid.UUID, str | None]:
        """Record the kickoff and hand back a scan id."""
        self.calls.append(list(repo_ids))
        return uuid.uuid4(), self.warning

    def install(self, monkeypatch: pytest.MonkeyPatch) -> ScanKickoffs:
        """Replace the job's scan kickoff (the scan itself has its own suite)."""
        monkeypatch.setattr(job_repo_bulk_clone, "kick_off_onboard_scan", self)
        return self


def onboard_item(full_name: str, main: str = "main", develop: str | None = None) -> dict[str, str]:
    """One picker row for ``POST /repos/bulk-onboard``."""
    item = {"fullName": full_name, "mainBranch": main}
    if develop is not None:
        item["developBranch"] = develop
    return item
