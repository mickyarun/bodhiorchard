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

"""Design generation must refuse when no design system applies.

The designer builds strictly from the design system's tokens and App Skeleton
and is told to stop rather than invent one, so with none resolvable the run can
only spend a model call, fail, and leave a failed design row behind. An org
tracking only backend repos has no design system and never will — that's a
legitimate state, so the refusal has to be an actionable 409, not a wasted run.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.bud_designs import _assert_design_system_available

_MOD = "app.api.v1.bud_designs"


async def _assert(effective: object | None, repo_ids: list[uuid.UUID | None]) -> None:
    with patch(
        f"{_MOD}.DesignSystemRefRepository",
        return_value=MagicMock(get_effective=AsyncMock(return_value=effective)),
    ):
        await _assert_design_system_available(MagicMock(), uuid.uuid4(), repo_ids)


@pytest.mark.asyncio
async def test_refuses_with_an_actionable_409_when_none_resolves() -> None:
    with pytest.raises(HTTPException) as exc:
        await _assert(None, [uuid.uuid4()])

    assert exc.value.status_code == 409
    # The message must name the fix — the user cannot act on "generation failed".
    assert "Design systems" in exc.value.detail


@pytest.mark.asyncio
async def test_allows_generation_when_a_design_system_resolves() -> None:
    """Regression guard: an org with a design system is untouched."""
    await _assert(MagicMock(), [uuid.uuid4()])


@pytest.mark.asyncio
async def test_the_default_repo_target_is_checked_too() -> None:
    """``repo_ids=[None]`` is the 'no specific repo' target and resolves via the
    org default — it must not skip the gate."""
    with pytest.raises(HTTPException):
        await _assert(None, [None])


@pytest.mark.asyncio
async def test_one_uncovered_repo_blocks_the_whole_request() -> None:
    """Generation fans out per repo; a repo with no design system would fail its
    own job, so refuse the batch rather than half-succeed."""
    covered, uncovered = uuid.uuid4(), uuid.uuid4()
    effective = {covered: MagicMock(), uncovered: None}
    with (
        patch(
            f"{_MOD}.DesignSystemRefRepository",
            return_value=MagicMock(
                get_effective=AsyncMock(side_effect=lambda rid: effective[rid])
            ),
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await _assert_design_system_available(MagicMock(), uuid.uuid4(), [covered, uncovered])

    assert exc.value.status_code == 409
