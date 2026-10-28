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

"""Hand-crafted vectors and a link runner for the bug linker integration tests.

Stored embeddings are the unit vector ``ANCHOR``; each other vector sits at
an exact cosine distance from it. Integer components keep pgvector's float4
storage exact, so "exactly at the threshold" is a real boundary.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.models.bug import Bug, BugSeverity, BugType
from app.services import bug_linker
from app.services.bug_linker import embed_and_link_bug
from tests.integration.scan_features_bugs_support import Factory, new_member, vec

ANCHOR = vec(1)
# Distances to ANCHOR: 3/5 → 0.40 exactly; 13/20 → 0.35 exactly.
BUD_AT = vec(3, 4)
BUD_BELOW = vec(301, 400)
BUD_ABOVE = vec(299, 400)
FEATURE_AT = vec(13, 15, 2, 1, 1)
FEATURE_BELOW = vec(1301, 1500, 200, 100, 100)
FEATURE_ABOVE = vec(1299, 1500, 200, 100, 100)


def embed_as(monkeypatch: pytest.MonkeyPatch, vector: list[float] | Exception) -> None:
    """Make the embedding model return ``vector`` (or raise it)."""

    async def _embed(text: str) -> list[float]:
        if isinstance(vector, Exception):
            raise vector
        return vector

    monkeypatch.setattr(bug_linker, "embedding_service", SimpleNamespace(embed=_embed))


async def link(
    factory: Factory,
    org: uuid.UUID,
    *,
    bug_type: BugType = BugType.TESTING,
    bud_id: uuid.UUID | None = None,
) -> tuple[object | None, Bug]:
    """File a bug in ``org``, run the linker, and return (match, bug as stored)."""
    reporter = await new_member(factory, org)
    async with factory() as db:
        bug = Bug(
            org_id=org,
            bug_number=1,
            title="Checkout button does nothing",
            description="Clicking pay is a no-op",
            severity=BugSeverity.HIGH,
            bug_type=bug_type,
            bud_id=bud_id,
            reporter_id=reporter,
        )
        db.add(bug)
        await db.flush()
        match = await embed_and_link_bug(db, org, bug)
        await db.commit()
        bug_id = bug.id
    async with factory() as db:
        stored = await db.get(Bug, bug_id)
    assert stored is not None
    return match, stored
