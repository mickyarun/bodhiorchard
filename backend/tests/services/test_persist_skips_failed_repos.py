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

"""The global persist phase must not stamp a repo whose scan failed.

``head_sha`` + ``last_scanned_at`` mean "this repo was fully scanned at this
SHA". Persist is global, so it also runs for a repo whose run died mid-pipeline;
stamping there makes the repo look complete, and the skip predicates, the
scan-history router and the PR-merge webhook all then trust a scan that never
finished. A healthy repo in the same scan must still be stamped — the failure of
one repo cannot strand the others.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scan.stages.persist_results import _drop_failed_repos

_MOD = "app.services.scan.stages.persist_results"

GOOD_PATH = "/repos/healthy"
BAD_PATH = "/repos/failed"


async def _drop(failed_paths: set[str]) -> dict[str, str]:
    new_shas = {GOOD_PATH: "aaaa1111", BAD_PATH: "bbbb2222"}
    with patch(
        f"{_MOD}.ScanRunRepository",
        return_value=MagicMock(
            list_failed_repo_paths_for_scan=AsyncMock(return_value=failed_paths)
        ),
    ):
        return await _drop_failed_repos(
            MagicMock(), org_id=uuid.uuid4(), scan_id=uuid.uuid4(), new_shas=new_shas
        )


@pytest.mark.asyncio
async def test_failed_repo_is_not_stamped_but_healthy_one_is() -> None:
    """The bug: a failed run stamped head_sha, so later scans skipped the work
    that never ran. Only the healthy repo may carry a SHA forward — one repo's
    failure must not strand the others."""
    result = await _drop({BAD_PATH})

    assert result == {GOOD_PATH: "aaaa1111"}


@pytest.mark.asyncio
async def test_all_repos_stamped_when_nothing_failed() -> None:
    """Regression guard: the happy path must be untouched."""
    result = await _drop(set())

    assert result == {GOOD_PATH: "aaaa1111", BAD_PATH: "bbbb2222"}


@pytest.mark.asyncio
async def test_a_failed_repo_outside_this_stamp_set_changes_nothing() -> None:
    """A failed repo that isn't being stamped anyway (no SHA collected) must not
    disturb the repos that are."""
    result = await _drop({"/repos/unrelated"})

    assert result == {GOOD_PATH: "aaaa1111", BAD_PATH: "bbbb2222"}
