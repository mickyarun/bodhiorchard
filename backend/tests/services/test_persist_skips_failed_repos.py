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

"""Only a repo that finished may be stamped as fully scanned.

``head_sha`` + ``last_scanned_at`` mean "this repo was fully scanned at this
SHA". Persist is global, so it also runs for repos whose run failed, was
cancelled, or was abandoned mid-flight by a dead worker. Stamping any of those
makes the repo look complete, and every SHA-gated stage then skips the work that
never ran — permanently, on a repo whose HEAD never moves again.

An allowlist is the point: "was fully scanned" is a positive claim. An earlier
version excluded only FAILED, which let CANCELLED and a stuck RUNNING through.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scan.stages.persist_results import _keep_completed_repos

_MOD = "app.services.scan.stages.persist_results"

GOOD_PATH = "/repos/healthy"
BAD_PATH = "/repos/incomplete"


async def _keep(completed: set[str]) -> dict[str, str]:
    new_shas = {GOOD_PATH: "aaaa1111", BAD_PATH: "bbbb2222"}
    with patch(
        f"{_MOD}.ScanRunRepository",
        return_value=MagicMock(
            list_completed_repo_paths_for_scan=AsyncMock(return_value=completed)
        ),
    ):
        return await _keep_completed_repos(
            MagicMock(), org_id=uuid.uuid4(), scan_id=uuid.uuid4(), new_shas=new_shas
        )


@pytest.mark.asyncio
async def test_only_the_completed_repo_is_stamped() -> None:
    """One repo's failure must not strand the others, nor stamp itself."""
    assert await _keep({GOOD_PATH}) == {GOOD_PATH: "aaaa1111"}


@pytest.mark.asyncio
async def test_all_repos_stamped_when_all_completed() -> None:
    """Regression guard: the happy path must be untouched."""
    assert await _keep({GOOD_PATH, BAD_PATH}) == {
        GOOD_PATH: "aaaa1111",
        BAD_PATH: "bbbb2222",
    }


@pytest.mark.asyncio
async def test_a_scan_where_nothing_completed_stamps_nothing() -> None:
    """A cancelled scan: no run reached a complete state, so no repo may carry a
    SHA forward claiming it was scanned."""
    assert await _keep(set()) == {}


@pytest.mark.asyncio
async def test_a_completed_path_outside_this_stamp_set_adds_nothing() -> None:
    """Completion of an unrelated repo cannot conjure a stamp for one whose SHA
    was never collected."""
    assert await _keep({GOOD_PATH, "/repos/unrelated"}) == {GOOD_PATH: "aaaa1111"}
