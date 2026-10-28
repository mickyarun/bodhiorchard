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

"""A design-phase BUD with a design system, the generate request and the designer's write."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from httpx import AsyncClient

from app.models.bud import BUDStatus
from tests.fakes.claude_script import ToolCall
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import Factory, auth_headers, seed_repo
from tests.integration.runner_internals.output_support import add_design_system
from tests.integration.runner_internals.stage_support import add_bud, seed_agent_org

WIREFRAME = "<!DOCTYPE html><html><body><h1>Refund</h1><button>Refund</button></body></html>"


@dataclass(frozen=True)
class DesignRun:
    """One generate request: the ids it returned."""

    org_id: uuid.UUID
    bud_id: uuid.UUID
    repo_id: uuid.UUID
    design_id: uuid.UUID
    job_id: str


async def generate_design(
    client: AsyncClient, factory: Factory, git_repo: LocalGitRepo
) -> DesignRun:
    """Seed a design-phase BUD with a design system and request generation."""
    org = await seed_agent_org(factory)
    repo_id = await seed_repo(factory, org.org_id, git_repo)
    await add_design_system(factory, org.org_id, repo_id)
    bud = await add_bud(factory, org.org_id, status=BUDStatus.DESIGN)
    response = await client.post(
        f"/api/v1/buds/{bud.id}/designs/generate",
        json={"repo_ids": [str(repo_id)]},
        headers=auth_headers(org.owner_id, org.org_id),
    )
    assert response.status_code == 202, response.text
    (row,) = response.json()
    return DesignRun(org.org_id, bud.id, repo_id, uuid.UUID(row["designId"]), row["jobId"])


def designer_write(
    run: DesignRun, *, bud_id: uuid.UUID | None = None, html: str = WIREFRAME
) -> ToolCall:
    """The designer's ``write_bud_design`` call for ``run``."""
    params = {
        "bud_id": str(bud_id or run.bud_id),
        "repo_id": str(run.repo_id),
        "design_id": str(run.design_id),
        "html": html,
    }
    return ToolCall("write_bud_design", params)
