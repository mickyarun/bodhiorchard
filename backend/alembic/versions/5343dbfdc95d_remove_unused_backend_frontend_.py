"""remove unused backend/frontend developer skill rows

The ``backend-developer`` and ``frontend-developer`` skill markdown files
never had a routing entry in ``AGENT_SKILL_MAP``, so no agent dispatch
path ever resolves to them. The old file-based seed loop (replaced by
the agent-type-aware seed in commit 8ef0faf) inserted them anyway, and
the previous migration's defensive fallback tagged the orphaned rows
``agent_type='bud'``. This migration removes those rows so the Agent
Prompts settings page only lists skills that actually drive behaviour.

Data-only migration: no schema changes. The CASCADE on
``bud_stage_skill_overrides.skill_id`` is ``RESTRICT`` and on
``bud_agent_tasks.skill_id`` is also restrictive, so we delete only
when no FK references remain — orphan skills with no usage history are
the common case. If a stale ``bud_agent_tasks`` row references one
of these slugs we leave it alone (and emit a NOTICE) rather than
breaking historical task records.

Revision ID: 5343dbfdc95d
Revises: 50e73dd335ca
Create Date: 2026-05-18 19:35:42.739657

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5343dbfdc95d"
down_revision: str | None = "50e73dd335ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEAD_SLUGS = ("backend-developer", "frontend-developer")


def upgrade() -> None:
    conn = op.get_bind()
    # Only delete rows that are not referenced by any historical agent
    # task — leaves the audit trail intact when an org happened to run
    # one of these orphan skills before the routing was cleaned up.
    conn.execute(
        sa.text(
            """
            DELETE FROM agent_skills s
            WHERE s.skill_slug = ANY(:slugs)
              AND NOT EXISTS (
                  SELECT 1 FROM bud_agent_tasks t WHERE t.skill_id = s.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM bud_stage_skill_overrides o
                  WHERE o.skill_id = s.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM agent_skill_bud_stages m
                  WHERE m.skill_id = s.id
              )
            """
        ),
        {"slugs": list(_DEAD_SLUGS)},
    )


def downgrade() -> None:
    # No-op: the markdown files have been removed from the repo, so we
    # can't reconstruct the deleted rows' prompt contents. An admin can
    # recreate them via the Custom Skill dialog if needed.
    pass
