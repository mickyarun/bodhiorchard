"""custom skills and per-bud stage overrides

Adds three columns to ``agent_skills`` (``agent_type``, ``is_default``,
``is_custom``) so each row is tied to exactly one of the 12 agent
types, and at most one default per ``(org_id, agent_type)`` is
enforceable. Backfill splits the two existing shared-slug seeds
(``product-manager`` → bud/standup/reassignment, ``testing`` →
bugLinker/testPlan) into one row per agent type so each can be
customised independently.

Adds ``bud_stage_skill_overrides`` for per-BUD stage skill choices set
via the create-BUD "Advanced settings" section.

Revision ID: 50e73dd335ca
Revises: zy_features_join_table
Create Date: 2026-05-18 17:43:56.948839

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "50e73dd335ca"
down_revision: str | None = "zy_features_join_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Inverse of app.agents.skill_mapping.AGENT_SKILL_MAP. Frozen here so the
# migration is independent of future code changes to that map.
SLUG_TO_AGENT_TYPES: dict[str, list[str]] = {
    "triage-analyst": ["triage"],
    "product-manager": ["bud", "standup", "reassignment"],
    "devops": ["status"],
    "technical-writer": ["learning"],
    "testing": ["bugLinker", "testPlan"],
    "code-reviewer": ["skill"],
    "tech-planner": ["techPlan"],
    "designer": ["design"],
    "slack-triage": ["slackTriage"],
}

_AGENT_TYPE_VALUES = (
    "triage",
    "bud",
    "status",
    "standup",
    "learning",
    "bugLinker",
    "reassignment",
    "skill",
    "techPlan",
    "testPlan",
    "design",
    "slackTriage",
)


def upgrade() -> None:
    agent_type_enum = sa.Enum(*_AGENT_TYPE_VALUES, name="agent_type")
    agent_type_enum.create(op.get_bind(), checkfirst=True)

    # 1. Add new columns. agent_type starts nullable; we backfill then
    #    ALTER to NOT NULL after the data step.
    op.add_column(
        "agent_skills",
        sa.Column("agent_type", agent_type_enum, nullable=True),
    )
    op.add_column(
        "agent_skills",
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "agent_skills",
        sa.Column("is_custom", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    # 2. Drop the old slug-only uniqueness — shared slugs will appear
    #    multiple times after the split.
    op.drop_constraint("uq_skill_org_slug", "agent_skills", type_="unique")

    # 3. Backfill: assign primary agent_type to existing rows, and clone
    #    rows for slugs that map to multiple agent types.
    conn = op.get_bind()
    for slug, agent_types in SLUG_TO_AGENT_TYPES.items():
        primary = agent_types[0]
        conn.execute(
            sa.text(
                "UPDATE agent_skills "
                "SET agent_type = CAST(:at AS agent_type), is_default = true "
                "WHERE skill_slug = :slug AND agent_type IS NULL"
            ),
            {"at": primary, "slug": slug},
        )
        for at in agent_types[1:]:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO agent_skills (
                        id, org_id, skill_slug, agent_type, is_default,
                        is_custom, name, description, tools, mcp_tools,
                        prompt, max_turns, timeout_seconds, model,
                        iteration_model, effort, created_at, updated_at
                    )
                    SELECT
                        gen_random_uuid(), org_id, skill_slug,
                        CAST(:at AS agent_type), true, false,
                        name, description, tools, mcp_tools, prompt,
                        max_turns, timeout_seconds, model, iteration_model,
                        effort, now(), now()
                    FROM agent_skills
                    WHERE skill_slug = :slug
                      AND agent_type = CAST(:primary AS agent_type)
                    """
                ),
                {"at": at, "slug": slug, "primary": primary},
            )

    # 4. Any rows whose slug is not in SLUG_TO_AGENT_TYPES (defensive: an
    #    org may have customised a skill with an unknown slug). Tag them
    #    'bud' as a sensible default; admin can re-target via the UI.
    conn.execute(
        sa.text(
            "UPDATE agent_skills "
            "SET agent_type = CAST('bud' AS agent_type), is_default = false "
            "WHERE agent_type IS NULL"
        )
    )

    # 5. Now safe to enforce NOT NULL.
    op.alter_column("agent_skills", "agent_type", nullable=False)

    # 6. New constraints.
    op.create_unique_constraint(
        "uq_skill_org_slug_agent_type",
        "agent_skills",
        ["org_id", "skill_slug", "agent_type"],
    )
    op.create_index(
        "uq_skill_one_default_per_agent_type",
        "agent_skills",
        ["org_id", "agent_type"],
        unique=True,
        postgresql_where="is_default = true",
    )

    # 7. New override table.
    op.create_table(
        "bud_stage_skill_overrides",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("bud_id", sa.UUID(), nullable=False),
        sa.Column(
            "bud_status",
            postgresql.ENUM(
                "bud",
                "design",
                "tech_arch",
                "development",
                "code_review",
                "testing",
                "uat",
                "prod",
                "closed",
                "discarded",
                name="bud_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bud_id"], ["bud_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["skill_id"], ["agent_skills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bud_id", "bud_status", name="uq_override_bud_status"),
    )
    op.create_index(
        op.f("ix_bud_stage_skill_overrides_bud_id"),
        "bud_stage_skill_overrides",
        ["bud_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bud_stage_skill_overrides_org_id"),
        "bud_stage_skill_overrides",
        ["org_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_bud_stage_skill_overrides_org_id"),
        table_name="bud_stage_skill_overrides",
    )
    op.drop_index(
        op.f("ix_bud_stage_skill_overrides_bud_id"),
        table_name="bud_stage_skill_overrides",
    )
    op.drop_table("bud_stage_skill_overrides")

    op.drop_index(
        "uq_skill_one_default_per_agent_type",
        table_name="agent_skills",
        postgresql_where="is_default = true",
    )
    op.drop_constraint("uq_skill_org_slug_agent_type", "agent_skills", type_="unique")

    # Collapse cloned rows back: keep one row per slug (the original).
    conn = op.get_bind()
    for slug, agent_types in SLUG_TO_AGENT_TYPES.items():
        if len(agent_types) <= 1:
            continue
        primary = agent_types[0]
        for at in agent_types[1:]:
            conn.execute(
                sa.text(
                    "DELETE FROM agent_skills "
                    "WHERE skill_slug = :slug "
                    "AND agent_type = CAST(:at AS agent_type)"
                ),
                {"slug": slug, "at": at},
            )
        # Restore the primary row's NULL-equivalent state (the column will
        # be dropped below, so this update is a no-op but kept for clarity).
        _ = primary

    op.create_unique_constraint(
        "uq_skill_org_slug",
        "agent_skills",
        ["org_id", "skill_slug"],
    )

    op.drop_column("agent_skills", "is_custom")
    op.drop_column("agent_skills", "is_default")
    op.drop_column("agent_skills", "agent_type")

    sa.Enum(name="agent_type").drop(op.get_bind(), checkfirst=True)
