"""remove todo-generator skill rows

The todo-generator skill no longer exists — TODOs are now derived
deterministically from the tech spec's ``## Implementation TODO``
section by ``app/services/todo_parser.py``. Per-org rows seeded under
``name='todo-generator'`` are orphaned by the file removal and must
be deleted so the activity log / settings UI don't surface a dead skill.

This is a data-only migration; the schema is untouched. ``downgrade()``
is a no-op because the rows are restored automatically on next app
start by ``seed_skills_for_org`` if the skill file is reintroduced.

Revision ID: 281bc0331ae5
Revises: 2c0717fc1c90
Create Date: 2026-05-13 17:59:46.795930

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "281bc0331ae5"
down_revision: str | None = "2c0717fc1c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEAD_SKILL_SLUG = "todo-generator"


def upgrade() -> None:
    # Drop any stage-mapping rows that reference the dead skill (FK in
    # ``agent_skill_bud_stages``) before deleting the skill row itself.
    op.execute(
        """
        DELETE FROM agent_skill_bud_stages
        WHERE skill_id IN (
            SELECT id FROM agent_skills WHERE skill_slug = '"""
        + _DEAD_SKILL_SLUG
        + """'
        )
        """
    )
    op.execute(f"DELETE FROM agent_skills WHERE skill_slug = '{_DEAD_SKILL_SLUG}'")


def downgrade() -> None:
    # No-op: rows are re-seeded automatically by seed_skills_for_org on
    # app start if the skill .md file is reintroduced.
    pass
