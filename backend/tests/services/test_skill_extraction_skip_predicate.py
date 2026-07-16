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

"""An unchanged HEAD must not stand in for "skills were already extracted".

The global persist phase stamps ``tracked.head_sha`` even when the repo's run
failed earlier in the pipeline. A scan that died before reaching skill
extraction therefore left HEAD looking already-scanned, and every later scan
skipped on the unchanged SHA — the repo never got skill profiles at all. These
tests pin the completed-step evidence that closes that, and the cache it must
still honour once the walk has genuinely run.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.scan_run_enums import StepStatus
from app.services.scan.stages._skip_predicates import should_skip_skill_extraction

SHA = "c191f7bcb0fa786b68c7b3904b6f3bbb90881fc6"

_MOD = "app.services.scan.stages._skip_predicates"


async def _decide(
    *,
    sha_matches: bool,
    latest_status: StepStatus | None,
    ever_completed: bool,
    full_rescan: bool = False,
) -> MagicMock:
    with (
        patch(
            f"{_MOD}._head_sha_matches_tracked",
            AsyncMock(return_value=(sha_matches, SHA if sha_matches else None)),
        ),
        patch(
            f"{_MOD}.find_latest_step_status_for_repo_phase",
            AsyncMock(return_value=latest_status),
        ),
        patch(
            f"{_MOD}.has_completed_step_for_repo_phase",
            AsyncMock(return_value=ever_completed),
        ),
    ):
        return await should_skip_skill_extraction(
            MagicMock(),
            org_id=uuid.uuid4(),
            repo_id=uuid.uuid4(),
            repo_path="/tmp/repo",
            full_rescan=full_rescan,
        )


@pytest.mark.asyncio
async def test_runs_when_the_stage_never_completed_despite_matching_sha() -> None:
    """The bug: a failed run stamped head_sha before skill extraction ever ran.
    An unchanged SHA must not be read as proof the walk happened."""
    decision = await _decide(sha_matches=True, latest_status=None, ever_completed=False)
    assert decision.skip is False
    assert "never completed" in (decision.reason or "")


@pytest.mark.asyncio
async def test_runs_when_only_cache_skips_were_ever_recorded() -> None:
    """SKIPPED_CACHE rows are not evidence of work — they are the symptom."""
    decision = await _decide(
        sha_matches=True, latest_status=StepStatus.SKIPPED_CACHE, ever_completed=False
    )
    assert decision.skip is False


@pytest.mark.asyncio
async def test_skips_once_the_walk_actually_completed_at_this_sha() -> None:
    """Regression guard: the SHA cache must still hold, or every scan re-walks."""
    decision = await _decide(
        sha_matches=True, latest_status=StepStatus.SKIPPED_CACHE, ever_completed=True
    )
    assert decision.skip is True
    assert decision.head_sha == SHA


@pytest.mark.asyncio
async def test_failed_prior_step_still_bypasses_before_the_completed_check() -> None:
    """A prior DONE plus a newer FAILED means retry — the existing bypass wins."""
    decision = await _decide(
        sha_matches=True, latest_status=StepStatus.FAILED, ever_completed=True
    )
    assert decision.skip is False
    assert "failed" in (decision.reason or "")


@pytest.mark.asyncio
async def test_changed_sha_runs_regardless_of_history() -> None:
    decision = await _decide(sha_matches=False, latest_status=None, ever_completed=True)
    assert decision.skip is False


@pytest.mark.asyncio
async def test_full_rescan_short_circuits_before_any_query() -> None:
    decision = await _decide(
        sha_matches=True, latest_status=None, ever_completed=True, full_rescan=True
    )
    assert decision.skip is False
    assert decision.reason == "full_rescan set"
