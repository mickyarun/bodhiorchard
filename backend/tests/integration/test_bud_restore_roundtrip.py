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

"""Discard → restore round trip against real Postgres.

The service-level tests stub the timeline repository and the feature
revive, so nothing there would notice if the JSONB predicate in
``latest_status_change_from`` stopped matching what ``record_event``
writes, or if ``get_by_source_ref`` grew an ``is_active`` filter (which
would quietly make every restore leave its feature soft-deleted). Both
are the kind of break that only a real query catches.

Covers:
  • the ``detail['to'] == 'discarded'`` predicate matching real event rows;
  • ``ORDER BY created_at DESC`` picking the LATEST discard after a
    discard → restore → discard cycle;
  • the feature round trip — deactivated on discard, active again on
    restore, with ``feature_status`` carried through untouched;
  • stale estimation dates being cleared so a restored BUD isn't
    instantly "lagging".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDocument, BUDStatus
from app.models.feature import Feature
from app.models.organization import Organization
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.feature import FeatureRepository
from app.services.bud_restore import restore_discarded_bud
from app.services.bud_timeline import record_event
from app.services.feature_lifecycle import transition_feature_for_bud

BUD_NUMBER = 7
BUD_REF = f"BUD-{BUD_NUMBER:03d}"


async def _seed(db: AsyncSession) -> tuple[Organization, BUDDocument, User]:
    org = Organization(name=f"Restore {uuid.uuid4()}", slug=f"rs-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()

    # Org membership lives in ``org_to_user``, not on the user row; the
    # restore only needs a real user for the timeline event's actor FK.
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Ada",
        password_hash="x",
    )
    db.add(user)
    bud = BUDDocument(
        org_id=org.id,
        bud_number=BUD_NUMBER,
        title="Payment retry logic",
        status=BUDStatus.DEVELOPMENT,
        # As the estimator would have left them before the discard.
        current_phase_deadline=datetime.now(UTC) - timedelta(days=21),
        prod_p70_date=datetime.now(UTC) - timedelta(days=14),
    )
    db.add(bud)
    await db.flush()
    return org, bud, user


async def _seed_feature(db: AsyncSession, org_id: uuid.UUID) -> Feature:
    """A BUD-authored feature, as ``create_planned_feature`` would leave it."""
    feature = Feature(
        org_id=org_id,
        feature_title="Feature: Payment retry",
        description="Retries failed payments.",
        capabilities={"capabilities": []},
        cluster_names=[],
        tags=[],
        cluster_signature=f"bud:{BUD_REF}",
        source="bud",
        source_ref=BUD_REF,
        feature_status="in_progress",
    )
    db.add(feature)
    await db.flush()
    return feature


async def _discard(
    db: AsyncSession, org: Organization, bud: BUDDocument, from_status: BUDStatus
) -> None:
    """Take the BUD through the real discard path."""
    await transition_feature_for_bud(db, org.id, bud.bud_number, BUDStatus.DISCARDED)
    await record_event(
        db,
        org.id,
        bud.id,
        "status_change",
        detail={"from": from_status.value, "to": BUDStatus.DISCARDED.value},
    )
    bud.status = BUDStatus.DISCARDED
    # Commit so this transition gets its own transaction clock. Postgres'
    # now() — which backs created_at — is transaction-scoped, so batching
    # several lifecycle steps into one transaction would stamp them all
    # identically and make "the newest discard" ambiguous. Production
    # never does that: every transition is its own request.
    await db.commit()


async def test_restore_returns_bud_to_its_pre_discard_phase_and_revives_the_feature(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as db:
        org, bud, user = await _seed(db)
        feature = await _seed_feature(db, org.id)
        actor = SimpleNamespace(id=user.id, org_id=org.id, name=user.name)

        await _discard(db, org, bud, BUDStatus.DEVELOPMENT)

        feat_repo = FeatureRepository(db, org_id=org.id)
        await db.refresh(feature)
        assert feature.is_active is False, "discard should soft-delete the feature"

        landed = await restore_discarded_bud(db, bud, actor)

        assert landed is BUDStatus.DEVELOPMENT
        assert bud.status is BUDStatus.DEVELOPMENT
        # Stale estimator output must not follow the BUD back — otherwise
        # list_lagging_in_statuses flags it as overdue on arrival.
        assert bud.current_phase_deadline is None
        assert bud.prod_p70_date is None

        # get_by_source_ref must keep finding soft-deleted rows, or the
        # revive silently no-ops and the feature stays deleted forever.
        revived = await feat_repo.get_by_source_ref(BUD_REF, source="bud")
        assert revived is not None
        assert revived.is_active is True
        assert revived.deactivated_at is None
        # Discard never touched feature_status, so restore must not either.
        assert revived.feature_status == "in_progress"


async def test_second_discard_restores_to_the_more_recent_phase(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """discard → restore → discard must resolve against the LATEST discard."""
    async with pg_session_factory() as db:
        org, bud, user = await _seed(db)
        await _seed_feature(db, org.id)
        actor = SimpleNamespace(id=user.id, org_id=org.id, name=user.name)

        await _discard(db, org, bud, BUDStatus.DEVELOPMENT)
        assert await restore_discarded_bud(db, bud, actor) is BUDStatus.DEVELOPMENT
        await db.commit()

        # Work moves on, then it's binned again from a later phase.
        bud.status = BUDStatus.TESTING
        await db.commit()
        await _discard(db, org, bud, BUDStatus.TESTING)

        assert await restore_discarded_bud(db, bud, actor) is BUDStatus.TESTING


async def test_restore_is_scoped_to_the_owning_org(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Another org's identically-numbered BUD must not leak its history.

    Both orgs have a BUD-007 discarded from different phases; the
    timeline lookup is org-scoped, so each restores to its own.
    """
    async with pg_session_factory() as db:
        org_a, bud_a, user_a = await _seed(db)
        org_b, bud_b, user_b = await _seed(db)
        actor_a = SimpleNamespace(id=user_a.id, org_id=org_a.id, name=user_a.name)

        await _discard(db, org_b, bud_b, BUDStatus.CODE_REVIEW)
        await _discard(db, org_a, bud_a, BUDStatus.DESIGN)

        assert await restore_discarded_bud(db, bud_a, actor_a) is BUDStatus.DESIGN
        # B is untouched by A's restore.
        refreshed_b = await BUDRepository(db, org_id=org_b.id).get_by_id(bud_b.id)
        assert refreshed_b is not None
        assert refreshed_b.status is BUDStatus.DISCARDED
