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

"""The wizard's finalize hands each repo to the scan once.

Two entries can name one checkout (sent twice, or spelled ``~/x`` and
``/home/me/x``). Both upsert the same row, and the repo id used to reach
``start_scan`` once per entry; the scan then ran two workflows on one
checkout at once. The real kickoff runs here; only ``start_scan`` and the
embedding check are replaced.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository
from app.schemas.setup import SetupSourceCode
from app.services import scan_kickoff
from app.services import setup_finalize_legacy as legacy

pytestmark = pytest.mark.integration


async def test_two_spellings_of_one_checkout_are_scanned_once(
    pg_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = (tmp_path / "home").resolve()
    repo = root / "svc"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    monkeypatch.setattr(legacy, "picker_roots", lambda: (root,))
    monkeypatch.setenv("HOME", str(root))
    started: list[list[uuid.UUID]] = []

    async def _embeddings_up() -> tuple[bool, str]:
        return True, ""

    async def _start_scan(*, repo_ids: list[uuid.UUID], **_: Any) -> uuid.UUID:
        started.append(list(repo_ids))
        return uuid.uuid4()

    monkeypatch.setattr(scan_kickoff.embedding_service, "check", _embeddings_up)
    monkeypatch.setattr(scan_kickoff, "start_scan", _start_scan)
    source = SetupSourceCode.model_validate(
        {"repos": [{"path": str(repo)}, {"path": "~/svc"}, {"path": f"{repo}/"}]}
    )

    async with pg_session_factory() as db:
        org = Organization(name="Dupes", slug=f"dupes-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        await legacy.finalize_legacy_source_code(org=org, source_code=source, db=db)
        rows = list(
            await db.scalars(
                select(TrackedRepository.id).where(TrackedRepository.org_id == org.id)
            )
        )

    assert len(rows) == 1
    assert started == [[rows[0]]]
