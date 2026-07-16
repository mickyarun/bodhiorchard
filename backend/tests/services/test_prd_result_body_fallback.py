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

"""The PRD handler must not drop an agent's authored requirements body.

Frontier models persist the body via the ``write_bud`` tool and leave only a
JSON fence in their final message. Smaller local models (Ollama) tend to answer
with the whole document as prose and skip the tool call. Without a fallback that
output is discarded and the BUD looks untouched despite a ``completed`` run.
These tests pin the fence-stripping and the "persist only when the tool didn't"
guard so neither regresses.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_result_handlers import (
    _strip_trailing_json_fence,
    handle_prd_result,
)

DOC = "## Problem Statement\n\nThe README is stale.\n\n## Acceptance Criteria\n\n- [ ] Rewritten"
FENCE = '```json\n{"linked_feature_ids": []}\n```'


def test_strips_trailing_fence_from_prose() -> None:
    assert _strip_trailing_json_fence(f"{DOC}\n\n{FENCE}") == DOC


def test_returns_body_unchanged_when_no_fence() -> None:
    assert _strip_trailing_json_fence(f"  {DOC}  ") == DOC


def test_fence_only_output_strips_to_empty() -> None:
    """A frontier model's final message is just the fence — nothing to store."""
    assert _strip_trailing_json_fence(FENCE) == ""


def test_in_body_json_example_survives_without_a_sentinel() -> None:
    """A model that skips write_bud may also skip the trailing sentinel fence.
    A ```json example inside the requirements must NOT be mistaken for it and
    truncate the doc — only the linked_feature_ids sentinel is stripped."""
    example = '```json\n{"endpoint": "/v1/readme"}\n```'
    doc_with_example = f"## API\n\n{example}\n\n## Acceptance Criteria\n\n- [ ] Done"
    assert _strip_trailing_json_fence(doc_with_example) == doc_with_example


def _bud(requirements_md: str) -> MagicMock:
    bud = MagicMock()
    bud.requirements_md = requirements_md
    bud.bud_number = 1
    return bud


async def _run(output: str, existing_requirements: str) -> MagicMock:
    """Drive handle_prd_result with its DB side effects mocked out."""
    bud = _bud(existing_requirements)
    db = MagicMock()
    db.flush = AsyncMock()
    with (
        patch(
            "app.services.agent_result_handlers._persist_pm_linked_features",
            AsyncMock(return_value=0),
        ),
        patch(
            "app.services.agent_result_handlers.BUDRepository",
            return_value=MagicMock(get_by_id=AsyncMock(return_value=bud)),
        ),
        patch("app.services.agent_result_handlers._snapshot_agent_write", AsyncMock()) as snapshot,
        patch("app.services.agent_result_handlers.estimate_bud_dates", AsyncMock()),
    ):
        # begin_nested is a sync context manager returning an async CM in prod;
        # the estimator is mocked, so a no-op async CM is enough here.
        db.begin_nested = MagicMock(return_value=_AsyncNull())
        await handle_prd_result(uuid.uuid4(), uuid.uuid4(), output, MagicMock(), db)
    return bud, snapshot


class _AsyncNull:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: Any) -> bool:
        return False


@pytest.mark.asyncio
async def test_persists_prose_body_when_tool_was_not_called() -> None:
    """Empty requirements + prose output → store the stripped body."""
    bud, snapshot = await _run(f"{DOC}\n\n{FENCE}", existing_requirements="")
    assert bud.requirements_md == DOC
    snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_does_not_clobber_a_successful_write_bud() -> None:
    """requirements_md already set by the tool → leave it, take no snapshot."""
    bud, snapshot = await _run(FENCE, existing_requirements="written by write_bud")
    assert bud.requirements_md == "written by write_bud"
    snapshot.assert_not_awaited()
