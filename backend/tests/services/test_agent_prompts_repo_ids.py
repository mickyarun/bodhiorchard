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

"""Stage-agent prompts give each repo's id, which the code-intel tools require.

The tech-plan agent was told to call ``code_stats({repo_id})`` but only saw
repo names and paths, so every call failed and it fell back to reading raw
files. These tests pin the id into every prompt that points at those tools.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_prompts import (
    _build_repo_context,
    _build_repo_diff_sections,
    build_code_review_prompt,
    build_tech_arch_prompt,
)

API_ID = uuid.uuid4()
WEB_ID = uuid.uuid4()
TRIPLES = [
    (API_ID, "/repos/taskflow-api", "taskflow-api"),
    (WEB_ID, "/repos/taskflow-web", "taskflow-web"),
]


def test_repo_context_lists_each_repo_with_its_id() -> None:
    context = _build_repo_context(TRIPLES)
    assert f"- **taskflow-api**: `/repos/taskflow-api` — repo_id: `{API_ID}`" in context
    assert f"- **taskflow-web**: `/repos/taskflow-web` — repo_id: `{WEB_ID}`" in context
    assert "not its name or path" in context


def test_repo_context_empty_without_repos() -> None:
    assert _build_repo_context([]) == ""


def test_diff_sections_carry_repo_id_when_known() -> None:
    sections, working_dir = _build_repo_diff_sections(
        [
            {"repo_path": "/repos/taskflow-api", "repo_name": "taskflow-api"},
            {"repo_path": "/repos/untracked", "repo_name": "untracked"},
        ],
        last_shas={},
        pr_branches={"taskflow-api": "bud-007/tags"},
        repo_ids_by_path={"/repos/taskflow-api": str(API_ID)},
    )
    assert working_dir == "/repos/taskflow-api"
    assert f"  - repo_id: `{API_ID}`\n  - PR branch: `bud-007/tags`" in sections[0]
    # A repo that no longer resolves to a tracked row still gets its diff
    # section, just without an id line.
    assert "repo_id" not in sections[1]


@pytest.mark.asyncio
async def test_tech_arch_prompt_includes_repo_ids() -> None:
    bud = MagicMock(id=uuid.uuid4(), bud_number=7, title="Task tags", designs=[])
    bud.requirements_md = "Users can tag tasks."
    skill = MagicMock(prompt="SKILL BODY")
    with (
        patch(
            "app.services.agent_prompts.TrackedRepoRepository",
            return_value=MagicMock(get_active_id_path_name=AsyncMock(return_value=TRIPLES)),
        ),
        patch(
            "app.repositories.design_system.DesignSystemRefRepository",
            return_value=MagicMock(get_default=AsyncMock(return_value=None)),
        ),
        patch(
            "app.services.agent_prompts.load_bud_agent_context",
            AsyncMock(return_value=MagicMock(linked_features=[])),
        ),
    ):
        prompt, working_dir = await build_tech_arch_prompt(bud, skill, uuid.uuid4(), MagicMock())

    assert working_dir == "/repos/taskflow-api"
    assert f"repo_id: `{API_ID}`" in prompt
    assert f"repo_id: `{WEB_ID}`" in prompt


@pytest.mark.asyncio
async def test_code_review_prompt_resolves_ids_from_confirmed_repo_paths() -> None:
    """``confirmed_repos`` stores no id, so the builder looks it up by path."""
    bud = MagicMock(id=uuid.uuid4(), bud_number=7, title="Task tags", designs=[])
    bud.metadata_ = {
        "confirmed_repos": [{"repo_path": "/repos/taskflow-api", "repo_name": "taskflow-api"}]
    }
    with (
        patch(
            "app.services.agent_prompts.TrackedRepoRepository",
            return_value=MagicMock(get_active_id_path_name=AsyncMock(return_value=TRIPLES)),
        ),
        patch(
            "app.repositories.dev_activity.DevActivityLogRepository",
            return_value=MagicMock(get_last_sha_per_repo=AsyncMock(return_value={})),
        ),
        patch(
            "app.repositories.pull_request.PullRequestRepository",
            return_value=MagicMock(list_for_bud=AsyncMock(return_value=[])),
        ),
        patch(
            "app.services.agent_prompts.load_bud_agent_context",
            AsyncMock(return_value=MagicMock(linked_features=[])),
        ),
    ):
        prompt, _ = await build_code_review_prompt(
            bud, MagicMock(prompt="SKILL"), uuid.uuid4(), MagicMock()
        )

    assert f"  - repo_id: `{API_ID}`" in prompt
    assert str(WEB_ID) not in prompt  # only confirmed repos are listed
