"""prune orphan agent_skills rows whose slug is no longer seeded

On prod, the BUD (PRD writer) section in Settings → Agent Prompts
showed a stray ``DevOps`` row alongside ``Product Manager``. Root
cause: an early version of ``seed_skills_for_org`` seeded every
``.md`` file in ``agents/skills/`` (including ``devops.md``), so a
row with ``skill_slug='devops'`` was created. A later rewrite of
``50e73dd335ca`` removed ``"devops": ["status"]`` from
``SLUG_TO_AGENT_TYPES`` after the runtime audit confirmed the status
agent never loads a skill. Step 4's "tag any remaining NULL
agent_type as 'bud'" defensive fallback then mislabelled the orphan
row as a BUD-agent skill.

This migration deletes any seeded row whose ``skill_slug`` is no
longer in the live ``AGENT_SKILL_MAP`` seed set — currently the
eight kebab-case slugs listed in ``_LIVE_SLUGS`` below.

Safety:
* ``is_custom = false`` predicate excludes user-created custom skills
  (those have arbitrary slugs by design).
* Same FK-safety guards as ``5343dbfdc95d`` — only delete rows that
  are not referenced by ``bud_agent_tasks``,
  ``bud_stage_skill_overrides``, or ``agent_skill_bud_stages``.
* ``agent_activity_logs.skill_id`` is nullable; we null those refs
  first so the audit trail (carried by the denormalised
  ``skill_slug`` text column) survives.

Fresh-install behaviour: a brand-new org's ``agent_skills`` table is
either empty (when the migration runs before seed) or populated only
with rows whose slug IS in ``_LIVE_SLUGS`` (after seed). The DELETE
predicate matches zero rows in both cases — no error, no surprise
data loss.

Revision ID: 15f415a484f1
Revises: 5343dbfdc95d
Create Date: 2026-05-19 09:52:58.233182
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "15f415a484f1"
down_revision: str | None = "5343dbfdc95d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirror of ``AGENT_SKILL_MAP.values()`` at this commit. Frozen here
# so the migration stays correct even if the map grows in a later
# release — a future addition will need its own migration to widen
# this allowlist, rather than letting this migration's effect drift.
_LIVE_SLUGS = (
    "triage-analyst",
    "product-manager",
    "technical-writer",
    "testing",
    "code-reviewer",
    "tech-planner",
    "designer",
    "slack-triage",
)


def upgrade() -> None:
    conn = op.get_bind()
    # Null out activity-log references first so the FK doesn't block
    # the DELETE. The denormalised ``skill_slug`` text column keeps
    # the audit trail readable after the underlying row is gone.
    conn.execute(
        sa.text(
            """
            UPDATE agent_activity_logs
            SET skill_id = NULL
            WHERE skill_id IN (
                SELECT id FROM agent_skills
                WHERE skill_slug != ALL(:slugs)
                  AND is_custom = false
            )
            """
        ),
        {"slugs": list(_LIVE_SLUGS)},
    )

    # Delete orphan seeded rows. ``is_custom = false`` protects
    # user-created skills (their slugs are arbitrary by design). The
    # NOT EXISTS predicates match ``5343dbfdc95d``'s safety contract:
    # never delete a row whose absence would dangle a FK from active
    # task / override / stage-mapping data.
    conn.execute(
        sa.text(
            """
            DELETE FROM agent_skills s
            WHERE s.skill_slug != ALL(:slugs)
              AND s.is_custom = false
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
        {"slugs": list(_LIVE_SLUGS)},
    )


def downgrade() -> None:
    # No-op: the dropped rows were seeded copies whose ``.md``
    # templates were also removed in earlier commits. There's no
    # lossless way to reconstruct them from this migration alone.
    # Restore the templates and run ``seed_skills_for_org`` if you
    # need them back.
    pass
