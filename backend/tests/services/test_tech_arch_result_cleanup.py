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

"""The saved tech spec is the spec alone — no chat lead-in, no insight blocks.

A run on 2026-10-27 stored "I've read through all the relevant code…" and a
``★ Insight`` block at the top of ``tech_spec_md``. These tests pin that the
handler strips both while still parsing the trailing impacted-repos fence.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_result_handlers import handle_tech_arch_result

API_ID = uuid.uuid4()
WEB_ID = uuid.uuid4()

SPEC = (
    "# BUD-007 — Task tags\n\n"
    "## Executive Summary\n\nAdd tags to tasks.\n\n"
    "## Files to Create or Modify\n\n| action | path | notes |\n|---|---|---|\n"
    "| modify | src/routes/tasks.ts | tag filter |"
)
CONTAMINATED_OUTPUT = (
    "`★ Insight ─────────────────────────────────────`\n"
    "- Tags live on the task row.\n"
    "`─────────────────────────────────────────────────`\n\n"
    "I've read through all the relevant code. Here's the draft tech spec:\n\n"
    f"{SPEC}\n\n"
    "## REQUIRED: Impacted Repos JSON\n\n"
    '```json\n{"impacted_repos": ["taskflow-api", "taskflow-web"], "summary": "both"}\n```\n'
)


class _AsyncNull:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: Any) -> bool:
        return False


async def _run(output: str) -> MagicMock:
    bud = MagicMock(assignee_id=None, bud_number=7)
    db = MagicMock(flush=AsyncMock(), begin_nested=MagicMock(return_value=_AsyncNull()))
    tracked = MagicMock(
        get_active_id_path_name=AsyncMock(
            return_value=[
                (API_ID, "/repos/taskflow-api", "taskflow-api"),
                (WEB_ID, "/repos/taskflow-web", "taskflow-web"),
            ]
        )
    )
    with (
        patch(
            "app.services.agent_result_handlers.BUDRepository",
            return_value=MagicMock(get_by_id=AsyncMock(return_value=bud)),
        ),
        patch("app.services.agent_result_handlers.TrackedRepoRepository", return_value=tracked),
        patch("app.services.agent_result_handlers._snapshot_agent_write", AsyncMock()),
        patch("app.services.agent_result_handlers.estimate_bud_dates", AsyncMock()),
    ):
        await handle_tech_arch_result(uuid.uuid4(), uuid.uuid4(), output, MagicMock(), db)
    return bud


@pytest.mark.asyncio
async def test_stored_spec_starts_at_its_heading() -> None:
    bud = await _run(CONTAMINATED_OUTPUT)
    assert bud.tech_spec_md == SPEC


@pytest.mark.asyncio
async def test_impacted_repos_still_parsed_from_contaminated_output() -> None:
    bud = await _run(CONTAMINATED_OUTPUT)
    assert bud.impacted_repos == [
        {"repo_id": str(API_ID), "repo_name": "taskflow-api"},
        {"repo_id": str(WEB_ID), "repo_name": "taskflow-web"},
    ]


@pytest.mark.asyncio
async def test_clean_output_is_stored_as_is() -> None:
    fence = '```json\n{"impacted_repos": ["taskflow-api"]}\n```'
    bud = await _run(f"{SPEC}\n\n{fence}\n")
    assert bud.tech_spec_md == SPEC
    assert bud.impacted_repos == [{"repo_id": str(API_ID), "repo_name": "taskflow-api"}]
