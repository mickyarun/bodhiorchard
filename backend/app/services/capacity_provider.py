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

"""Role-pool capacity provider for the AI-PERT estimation engine.

Capacity here is "what fraction of one full working day across the pool
that can serve this phase is free right now?". The estimator divides each
phase's effort sample by this number to get wall-clock days. Capacity =
1.0 means a fresh pool sitting idle; capacity = 0.4 means the pool is
~60 % loaded.

Why role-level (not per-person): the smart-assignment agent picks the
actual assignee at the start of each phase. Per-person availability is
unknowable at estimation time, so we work at the role-pool granularity
and let the assignment agent do its own load balancing later.

Why the *chain* pool (not the single owning role): every phase has a
``PHASE_ROLE_CHAIN`` — a primary owner plus degrade-by-adjacency
fallbacks (a small team with one designer still gets design done by a PM
or developer). The assignment agent already routes through that chain, so
capacity counts the same pool; otherwise a lone specialist (1 designer,
1 tech-lead) reads as permanently maxed-out even though the work clearly
ships. Active load is taken from the *primary* role only — a deliberate
optimism about fallbacks: we credit the fallback pool's headcount without
subtracting its own primary commitments. Modelling that cross-phase
contention properly needs a global allocation solver; here we err toward
the fallback being available, which is the right direction given the
old subtractive model bottomed every understaffed role out at the floor.

Math: ``capacity = chain_pool / (chain_pool + primary_active)``. This
M/M/1-style availability ratio is bounded in (0, 1] and degrades
smoothly toward (never to) zero as load grows — no cliff. The engine
still floors the divisor at ``MIN_CAPACITY`` as a divide-by-zero guard
for pathological overload (active ≫ pool).
"""

import uuid
from typing import NamedTuple

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.user import UserRole
from app.repositories.user import UserRepository
from app.services.phase_roles import PHASE_ROLE_CHAIN, PHASE_ROLE_MAP

logger = structlog.get_logger(__name__)

_TERMINAL_STATUSES = {BUDStatus.PROD, BUDStatus.CLOSED, BUDStatus.DISCARDED}


class RoleLoad(NamedTuple):
    """Raw pool size and active in-flight load for one role.

    Kept un-collapsed (not pre-divided into a capacity float) so the
    chain-aware phase projection downstream can sum pools across a
    fallback chain before applying the queueing curve.
    """

    pool: int
    active: int


async def get_role_loads(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> dict[UserRole, RoleLoad]:
    """Return raw ``(pool, active)`` per role for one org.

    Issues two aggregate queries (no per-row work):
      1. Pool size: how many users hold each role in this org.
      2. Active load: how many non-terminal BUDs are in a status whose
         mapped role matches each role.

    The queueing curve and chain pooling live in the pure ``*_capacity``
    helpers below so they can be unit-tested without a session. Every
    role in :class:`UserRole` is present in the result (pool/active
    default to 0) so callers never KeyError.
    """
    pool_by_role = await UserRepository(db).count_active_by_role(org_id)

    active_query = (
        select(BUDDocument.status, func.count())
        .where(
            BUDDocument.org_id == org_id,
            BUDDocument.status.notin_([s.value for s in _TERMINAL_STATUSES]),
        )
        .group_by(BUDDocument.status)
    )
    active_rows = (await db.execute(active_query)).all()

    active_by_role: dict[UserRole, int] = {}
    for status_value, count in active_rows:
        # SQLAlchemy returns the enum instance when the column is mapped as
        # BUDStatus and a plain string when it's read after a raw value
        # comparison. Normalise before keying the phase map — matches the
        # isinstance check used in estimation_context.py:94,120.
        phase = status_value.value if isinstance(status_value, BUDStatus) else status_value
        role = PHASE_ROLE_MAP.get(phase)
        if role is None:
            continue
        active_by_role[role] = active_by_role.get(role, 0) + count

    return {
        role: RoleLoad(pool=pool_by_role.get(role, 0), active=active_by_role.get(role, 0))
        for role in UserRole
    }


def phase_capacity(
    role_loads: dict[UserRole, RoleLoad],
    phase: str,
) -> float:
    """Chain-aware queueing capacity in (0, 1] for a single phase.

    Pool is summed across the phase's full ``PHASE_ROLE_CHAIN`` (primary
    owner + fallbacks); active load is the primary role's in-flight count
    (which already aggregates every phase that role owns). Returns 1.0 —
    no adjustment — for an unknown phase or one with literally nobody in
    its chain (an unstaffable phase is the assignment banner's problem,
    not a number we should silently inflate). A pool with zero active
    load yields exactly 1.0.
    """
    chain = PHASE_ROLE_CHAIN.get(phase)
    if not chain:
        return 1.0

    pool = sum(role_loads.get(role, RoleLoad(0, 0)).pool for role in chain)
    active = role_loads.get(chain[0], RoleLoad(0, 0)).active

    if pool == 0:
        if active > 0:
            logger.warning(
                "capacity_chain_pool_empty_but_active",
                phase=phase,
                chain=[r.value for r in chain],
                active_buds=active,
                action="defaulting capacity to 1.0; staff at least one role in this chain",
            )
        return 1.0

    return pool / (pool + active)


def capacity_by_phase(
    role_loads: dict[UserRole, RoleLoad],
    phase_order: list[str],
) -> dict[str, float]:
    """Project raw role loads onto a per-phase capacity dict for the engine.

    Pure function — kept separate from the DB query so it can be
    exercised without a session. Each phase is independently scored via
    :func:`phase_capacity`.
    """
    return {phase: phase_capacity(role_loads, phase) for phase in phase_order}
