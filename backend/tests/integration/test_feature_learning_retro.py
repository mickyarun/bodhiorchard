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

"""Resilience tests for ``FeatureLearningRepository.set_retrospective``.

Regression cover for the BUD-029/036 incident: a transient
``compute_and_persist`` failure at close left no ``feature_learnings``
row, and because ``set_retrospective`` was update-only the post-close
Learning Agent silently dropped its recap. ``set_retrospective`` is now
create-if-missing so the qualitative recap survives a missing metrics
envelope; the next ``compute_and_persist`` backfills the quantitative
half.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDocument, BUDStatus
from app.models.organization import Organization
from app.repositories.feature_learning import FeatureLearningRepository


async def _make_closed_bud(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    org = Organization(name=f"Retro {uuid.uuid4()}", slug=f"retro-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    bud = BUDDocument(
        org_id=org.id,
        bud_number=29,
        title="Multi-URL Webhook Endpoints",
        status=BUDStatus.CLOSED,
    )
    db.add(bud)
    await db.flush()
    return org.id, bud.id


async def test_set_retrospective_creates_row_when_metrics_missing(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No row yet (compute failed at close) → the recap creates one.

    ``metrics`` stays NULL so the next ``compute_and_persist`` pass — whose
    skip-if-rich guard keys on ``metrics is not None`` — still runs and
    backfills the quantitative half.
    """
    async with pg_session_factory() as db:
        org_id, bud_id = await _make_closed_bud(db)
        repo = FeatureLearningRepository(db, org_id=org_id)

        assert await repo.get_for_bud(bud_id) is None

        row = await repo.set_retrospective(
            bud_id, retrospective_md="## Recap\nShipped late.", embedding=None
        )

        assert row.bud_id == bud_id
        assert row.retrospective_md == "## Recap\nShipped late."
        assert row.metrics is None
        assert row.bug_count == 0


async def test_set_retrospective_updates_existing_row_and_keeps_metrics(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An existing metrics row gets its recap filled without losing metrics."""
    async with pg_session_factory() as db:
        org_id, bud_id = await _make_closed_bud(db)
        repo = FeatureLearningRepository(db, org_id=org_id)

        await repo.upsert_for_bud(
            bud_id,
            cycle_time_days=14.68,
            estimated_days=10.0,
            bug_count=3,
            metrics={"phase_metrics": {"development": {"drift_pct": 12.0}}},
        )

        row = await repo.set_retrospective(
            bud_id, retrospective_md="## Recap\nTwo bugs.", embedding=None
        )

        assert row.retrospective_md == "## Recap\nTwo bugs."
        assert row.metrics == {"phase_metrics": {"development": {"drift_pct": 12.0}}}
        # cycle_time_days is a Numeric column → Decimal on read-back.
        assert row.cycle_time_days is not None
        assert float(row.cycle_time_days) == 14.68
        assert row.bug_count == 3
