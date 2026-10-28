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

"""Agent outputs shaped like each stage's skill asks for, and reads for what they write."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.bud import BUDDesign
from app.models.bud_version import BUDVersion
from app.models.feature_learning import FeatureLearning
from app.models.notification import Notification
from app.repositories import bud_version as bud_version_repo
from app.repositories.bud import BUDDesignRepository
from app.repositories.design_system import DesignSystemRefRepository
from app.repositories.feature_learning import FeatureLearningRepository
from app.repositories.notification import NotificationRepository
from app.services.feature_lifecycle import create_planned_feature
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentRun
from tests.fakes.seed import Factory
from tests.integration.runner_internals.stage_support import ESTIMATE_MARKER

TECH_SPEC = "# Tech spec: refunds\n\n## Changes\n\n- add `refund()` to orders"


def json_fence(payload: dict[str, Any]) -> str:
    """A fenced JSON block as the skills tell the agent to end with."""
    return f"```json\n{json.dumps(payload)}\n```"


def tech_arch_output(*repo_names: str) -> str:
    """A tech spec followed by the required impacted-repos heading and fence."""
    fence = json_fence({"impacted_repos": list(repo_names), "summary": "orders change"})
    return f"{TECH_SPEC}\n\n## REQUIRED: Impacted Repos JSON\n\n{fence}"


def qa_output(*, automation: int, manual: int) -> str:
    """The testing skill's JSON answer with numbered cases."""
    payload = {
        "automation_test_cases": [
            {"id": f"TC-{i:03d}", "title": f"auto {i}"} for i in range(1, automation + 1)
        ],
        "manual_test_cases": [
            {"id": f"TC-{i:03d}", "title": f"manual {i}"}
            for i in range(automation + 1, automation + manual + 1)
        ],
        "test_execution_plan": "Run unit tests, then manual checks.",
    }
    return json.dumps(payload)


def stage_runs(fake: FakeClaudeRunner) -> list[AgentRun]:
    """Agent runs other than the estimator's follow-up runs."""
    return [run for run in fake.runs if ESTIMATE_MARKER not in run.prompt]


async def planned_feature(factory: Factory, org_id: uuid.UUID, title: str) -> uuid.UUID:
    """A planned feature row the PM agent can link to."""
    async with factory() as db:
        feature = await create_planned_feature(db, org_id, 900, title, f"{title} body")
        await db.commit()
        return feature.id


async def versions(factory: Factory, bud_id: uuid.UUID) -> list[BUDVersion]:
    """History snapshots for the BUD, newest first."""
    async with factory() as db:
        return await bud_version_repo.list_for_bud(db, bud_id)


async def learning(
    factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID
) -> FeatureLearning | None:
    """The BUD's learning row, if any."""
    async with factory() as db:
        return await FeatureLearningRepository(db, org_id=org_id).get_for_bud(bud_id)


async def notifications(factory: Factory, user_id: uuid.UUID) -> list[Notification]:
    """The user's active in-app notifications, newest first."""
    async with factory() as db:
        return await NotificationRepository(db, user_id=user_id).list_active()


async def add_design_system(factory: Factory, org_id: uuid.UUID, repo_id: uuid.UUID) -> None:
    """A default design system for ``repo_id`` so design generation is allowed."""
    async with factory() as db:
        await DesignSystemRefRepository(db, org_id=org_id).upsert(
            repo_id=repo_id,
            content="# Tokens\n\n--brand: #0a7",
            source_hash="hash",
            extracted_at=datetime.now(UTC),
            is_default=True,
        )
        await db.commit()


async def load_design(factory: Factory, org_id: uuid.UUID, design_id: uuid.UUID) -> BUDDesign:
    """A fresh read of a design row."""
    async with factory() as db:
        design = await BUDDesignRepository(db, org_id=org_id).get_by_id(design_id)
        assert design is not None
        return design
