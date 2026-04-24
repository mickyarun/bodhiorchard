# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Role-pool capacity provider for the AI-PERT estimation engine.

Capacity here is "what fraction of one full working day across this role
pool is free right now?". The estimator divides each phase's effort
sample by this number to get wall-clock days. Capacity = 1.0 means a
fresh role pool sitting idle; capacity = 0.4 means the pool is 60 %
loaded.

Why role-level (not per-person): the smart-assignment agent picks the
actual assignee at the start of each phase. Per-person availability is
unknowable at estimation time, so we work at the role-pool granularity
and let the assignment agent do its own load balancing later.

Math: ``capacity = max(MIN_CAPACITY, 1 − active_buds_in_role / pool_size)``.
The floor exists so the wall-clock divisor never explodes when a single
role is over-subscribed (the 0.1 floor implies a 10× stretch ceiling,
which is the sane upper bound for "this team is in firefighting mode").
"""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.user import OrgToUser, UserRole
from app.services.estimation_engine import MIN_CAPACITY
from app.services.phase_roles import PHASE_ROLE_MAP

logger = structlog.get_logger(__name__)

_TERMINAL_STATUSES = {BUDStatus.PROD, BUDStatus.CLOSED, BUDStatus.DISCARDED}


async def get_role_capacity(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> dict[UserRole, float]:
    """Return current capacity per role for one org.

    Issues two aggregate queries (no per-row work):
      1. Pool size: how many users hold each role in this org.
      2. Active load: how many non-terminal BUDs are in a status whose
         mapped role matches each role.

    Roles with zero pool size return 1.0 with a structlog warning so the
    gap is observable rather than silently absorbing the over-load
    signal. Roles never seen in this org default to 1.0 too.
    """
    pool_query = (
        select(OrgToUser.role, func.count())
        .where(OrgToUser.org_id == org_id)
        .group_by(OrgToUser.role)
    )
    pool_rows = (await db.execute(pool_query)).all()
    pool_by_role: dict[UserRole, int] = {row[0]: row[1] for row in pool_rows}

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

    capacity: dict[UserRole, float] = {}
    for role in UserRole:
        pool_size = pool_by_role.get(role, 0)
        active = active_by_role.get(role, 0)
        if pool_size == 0:
            if active > 0:
                logger.warning(
                    "capacity_role_pool_empty_but_active",
                    org_id=str(org_id),
                    role=role.value,
                    active_buds=active,
                    action="defaulting capacity to 1.0; assign at least one user this role",
                )
            capacity[role] = 1.0
            continue
        capacity[role] = max(MIN_CAPACITY, 1.0 - active / pool_size)
    return capacity


def capacity_by_phase(
    role_capacity: dict[UserRole, float],
    phase_order: list[str],
) -> dict[str, float]:
    """Project per-role capacity onto a per-phase dict the engine can consume.

    Pure function — kept separate from the DB query so it can be
    exercised without a session and so any future per-org overrides on
    the phase→role map slot in here without touching the SQL path.
    """
    out: dict[str, float] = {}
    for phase in phase_order:
        role = PHASE_ROLE_MAP.get(phase)
        if role is None:
            out[phase] = 1.0
            continue
        out[phase] = role_capacity.get(role, 1.0)
    return out
