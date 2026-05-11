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

"""Rename PRD to BUD with botanical lifecycle statuses.

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-03-20 12:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision: str = "i9d0e1f2a3b4"
down_revision: str | None = "h8c9d0e1f2a3"
branch_labels: str | None = None
depends_on: str | None = None

# Status mapping: old PRD statuses → new BUD botanical stages
STATUS_MAP = {
    "draft": "seed",
    "design": "sprout",
    "tech-spec": "sapling",
    "in-dev": "growing",
    "in-qa": "budding",
    "in-uat": "blooming",
    "deployed": "fruiting",
    "cancelled": "wilted",
}

REVERSE_MAP = {v: k for k, v in STATUS_MAP.items()}


def upgrade() -> None:
    # 1. Create new bud_status enum
    bud_status = sa.Enum(
        "seed",
        "sprout",
        "sapling",
        "growing",
        "budding",
        "blooming",
        "fruiting",
        "wilted",
        name="bud_status",
    )
    bud_status.create(op.get_bind(), checkfirst=True)

    # 2. Add temporary column with new enum type
    op.add_column("prd_documents", sa.Column("status_new", bud_status, nullable=True))

    # 3. Migrate status values
    for old_val, new_val in STATUS_MAP.items():
        op.execute(
            sa.text(
                "UPDATE prd_documents SET status_new = CAST(:new_val AS bud_status) "
                "WHERE status = CAST(:old_val AS prd_status)"
            ).bindparams(new_val=new_val, old_val=old_val)
        )

    # 4. Drop old status column and rename new one
    op.drop_column("prd_documents", "status")
    op.alter_column("prd_documents", "status_new", new_column_name="status", nullable=False)

    # 5. Drop old prd_status enum
    op.execute(sa.text("DROP TYPE IF EXISTS prd_status"))

    # 6. Rename table prd_documents → bud_documents
    op.rename_table("prd_documents", "bud_documents")

    # 7. Rename column prd_number → bud_number
    op.alter_column("bud_documents", "prd_number", new_column_name="bud_number")

    # 8. Drop old constraints/indexes, create new ones
    op.drop_constraint("uq_prd_org_number", "bud_documents", type_="unique")
    op.create_unique_constraint("uq_bud_org_number", "bud_documents", ["org_id", "bud_number"])

    op.execute(sa.text("DROP INDEX IF EXISTS ix_prd_org_status"))
    op.create_index("ix_bud_org_status", "bud_documents", ["org_id", "status"])

    # 9. Update FK columns in bugs table (prd_id → bud_id)
    op.alter_column("bugs", "prd_id", new_column_name="bud_id")

    # 10. Update FK columns in feature_learnings table (prd_id → bud_id)
    op.alter_column("feature_learnings", "prd_id", new_column_name="bud_id")

    # 11. Update knowledge_items: source='prd' → 'bud', source_ref 'PRD-NNN' → 'BUD-NNN'
    op.execute(sa.text("UPDATE knowledge_items SET source = 'bud' WHERE source = 'prd'"))
    op.execute(
        sa.text(
            "UPDATE knowledge_items SET source_ref = REPLACE(source_ref, 'PRD-', 'BUD-') "
            "WHERE source_ref LIKE 'PRD-%'"
        )
    )

    # 12. Update permission records: prds:* → buds:*
    op.execute(
        sa.text(
            "UPDATE permissions SET resource_id = REPLACE(resource_id, 'prds:', 'buds:') "
            "WHERE resource_id LIKE 'prds:%'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE permissions SET name = REPLACE(name, 'PRDs', 'BUDs') WHERE name LIKE '%PRDs%'"
        )
    )


def downgrade() -> None:
    # Reverse: BUD → PRD

    # 1. Recreate old prd_status enum
    prd_status = sa.Enum(
        "draft",
        "design",
        "tech-spec",
        "in-dev",
        "in-qa",
        "in-uat",
        "deployed",
        "cancelled",
        name="prd_status",
    )
    prd_status.create(op.get_bind(), checkfirst=True)

    # 2. Add temporary column with old enum type
    op.add_column("bud_documents", sa.Column("status_old", prd_status, nullable=True))

    # 3. Migrate status values back
    for new_val, old_val in REVERSE_MAP.items():
        op.execute(
            sa.text(
                "UPDATE bud_documents SET status_old = CAST(:old_val AS prd_status) "
                "WHERE status = CAST(:new_val AS bud_status)"
            ).bindparams(old_val=old_val, new_val=new_val)
        )

    # 4. Drop new status column and rename old one
    op.drop_column("bud_documents", "status")
    op.alter_column("bud_documents", "status_old", new_column_name="status", nullable=False)

    # 5. Drop bud_status enum
    op.execute(sa.text("DROP TYPE IF EXISTS bud_status"))

    # 6. Rename table back
    op.rename_table("bud_documents", "prd_documents")

    # 7. Rename column back
    op.alter_column("prd_documents", "bud_number", new_column_name="prd_number")

    # 8. Recreate old constraints/indexes
    op.drop_constraint("uq_bud_org_number", "prd_documents", type_="unique")
    op.create_unique_constraint("uq_prd_org_number", "prd_documents", ["org_id", "prd_number"])

    op.execute(sa.text("DROP INDEX IF EXISTS ix_bud_org_status"))
    op.create_index("ix_prd_org_status", "prd_documents", ["org_id", "status"])

    # 9. Rename FK columns back
    op.alter_column("bugs", "bud_id", new_column_name="prd_id")
    op.alter_column("feature_learnings", "bud_id", new_column_name="prd_id")

    # 10. Revert knowledge_items
    op.execute(sa.text("UPDATE knowledge_items SET source = 'prd' WHERE source = 'bud'"))
    op.execute(
        sa.text(
            "UPDATE knowledge_items SET source_ref = REPLACE(source_ref, 'BUD-', 'PRD-') "
            "WHERE source_ref LIKE 'BUD-%'"
        )
    )

    # 11. Revert permissions
    op.execute(
        sa.text(
            "UPDATE permissions SET resource_id = REPLACE(resource_id, 'buds:', 'prds:') "
            "WHERE resource_id LIKE 'buds:%'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE permissions SET name = REPLACE(name, 'BUDs', 'PRDs') WHERE name LIKE '%BUDs%'"
        )
    )
