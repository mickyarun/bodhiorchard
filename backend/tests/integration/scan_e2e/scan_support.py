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

"""Shared setup for the end-to-end scan tests.

The synthesis "agent" is scripted to read the cluster payload out of the
real synthesis prompt and file one feature per cluster through the real
``write_synthesis_feature`` MCP tool, the way the model is told to.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from functools import partial
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.scan import Scan
from app.models.scan_repo_run import ScanRepoRun
from app.models.scan_repo_step import ScanRepoStep
from app.models.tracked_repository import TrackedRepository
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.feature import FeatureRepository
from app.repositories.repo_graph_cache import RepoGraphCacheRepository
from app.repositories.scan import ScanRepository
from app.repositories.scan_run import ScanRunRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.scan.runner import wait_for_scan_task
from tests.fakes.claude_script import AgentRun, AgentScript, ToolCall

Factory = async_sessionmaker[AsyncSession]
SYNTHESIS_MARKER = "write_synthesis_feature"
NARROW_MARKER = "after a PR merge"
SCANS_URL = "/api/v1/reposcanv2/scans"
_REPO_ID_RE = re.compile(r"``repo_id``: ([0-9a-f-]{36})")
_PAYLOAD_RE = re.compile(r'\[\s*\{\s*"community_id"')


def prompt_clusters(prompt: str) -> list[dict[str, Any]]:
    """The cluster payload embedded in a full or narrow synthesis prompt."""
    match = _PAYLOAD_RE.search(prompt)
    assert match is not None, "no cluster payload in the synthesis prompt"
    payload, _ = json.JSONDecoder().raw_decode(prompt, match.start())
    return list(payload)


def feature_params(run: AgentRun, index: int, prefix: str = "Capability") -> dict[str, Any]:
    """``write_synthesis_feature`` params for the ``index``-th cluster in the prompt."""
    cluster = prompt_clusters(run.prompt)[index]
    repo_id = _REPO_ID_RE.search(run.prompt)
    label = cluster["label"] or "+".join(cluster["cluster_ids"])
    return {
        "name": f"{prefix} {label}",
        "description": f"{prefix}: handles {label} for the shop service.",
        "source_community_ids": cluster["cluster_ids"],
        "repo_name": "shop-api",
        "repo_id": repo_id.group(1) if repo_id else None,
        "capabilities": [f"manage {label}"],
    }


def synthesis_writing(feature_count: int, prefix: str = "Capability") -> AgentScript:
    """A synthesis run that files one feature for each of the first N clusters."""
    steps = [
        ToolCall(SYNTHESIS_MARKER, partial(feature_params, index=i, prefix=prefix))
        for i in range(feature_count)
    ]
    return AgentScript.ok("Synthesis complete.", *steps)


@dataclass(frozen=True)
class ScanOutcome:
    """What one finished scan left in the database."""

    scan: Scan
    runs: list[ScanRepoRun]
    steps: list[ScanRepoStep]

    @property
    def run(self) -> ScanRepoRun:
        """The only repo run of a single-repo scan."""
        (only,) = self.runs
        return only


async def start_scan_over_http(
    client: AsyncClient,
    headers: dict[str, str],
    repo_id: uuid.UUID,
    *,
    full_rescan: bool = False,
) -> uuid.UUID:
    """POST the scan like the UI does and wait for the background fanout."""
    body = {"repo_ids": [str(repo_id)], "config": {"full_rescan": full_rescan}}
    response = await client.post(SCANS_URL, json=body, headers=headers)
    assert response.status_code == 202, response.text
    scan_id = uuid.UUID(response.json()["scan_id"])
    await wait_for_scan_task(scan_id)
    return scan_id


async def load_outcome(factory: Factory, org_id: uuid.UUID, scan_id: uuid.UUID) -> ScanOutcome:
    """The scan row, its repo runs and every step row."""
    async with factory() as db:
        scan = await ScanRepository(db, org_id=org_id).get(scan_id)
        assert scan is not None
        run_repo = ScanRunRepository(db, org_id=org_id)
        runs = await run_repo.find_for_scan(scan_id=scan_id)
        steps: list[ScanRepoStep] = []
        for run in runs:
            steps.extend(await run_repo.find_steps_for_run(scan_repo_run_id=run.id))
        return ScanOutcome(scan=scan, runs=runs, steps=steps)


async def active_feature_titles(
    factory: Factory, org_id: uuid.UUID, repo_id: uuid.UUID
) -> set[str]:
    """Titles of the repo's active features."""
    async with factory() as db:
        rows = await FeatureRepository(db, org_id=org_id).list_current_for_repo(repo_id)
        return {row.feature_title for row in rows if row.is_active}


async def active_last_seen(
    factory: Factory, org_id: uuid.UUID, repo_id: uuid.UUID
) -> dict[str, str | None]:
    """Title to ``last_seen_sha`` of the repo's active features."""
    async with factory() as db:
        rows = await FeatureRepository(db, org_id=org_id).list_current_for_repo(repo_id)
        return {row.feature_title: row.last_seen_sha for row in rows if row.is_active}


async def cache_counts(
    factory: Factory, org_id: uuid.UUID, repo_id: uuid.UUID, head_sha: str
) -> tuple[int, bool]:
    """``(cluster_cache rows, repo_graph_cache present)`` for one SHA."""
    async with factory() as db:
        clusters = await ClusterCacheRepository(db, org_id=org_id).list_for_repo_sha(
            repo_id=repo_id, head_sha=head_sha
        )
        graph = await RepoGraphCacheRepository(db, org_id=org_id).get_for_sha(
            repo_id=repo_id, head_sha=head_sha
        )
        return len(clusters), graph is not None


async def tracked_repo(
    factory: Factory, org_id: uuid.UUID, repo_id: uuid.UUID
) -> TrackedRepository:
    """The tracked repository row as the scan left it."""
    async with factory() as db:
        row = await TrackedRepoRepository(db, org_id=org_id).get_by_id(repo_id)
        assert row is not None
        return row
