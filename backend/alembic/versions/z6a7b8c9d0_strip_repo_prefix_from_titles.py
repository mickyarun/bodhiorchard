"""Strip [RepoName] prefix from feature titles and dedup collisions.

Revision ID: z6a7b8c9d0
Revises: 84cf56c5f2d8
Create Date: 2026-03-24
"""

from alembic import op

revision = "z6a7b8c9d0"
down_revision = "84cf56c5f2d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Strip [RepoName] prefix from feature_registry titles.

    1. Remove ``[RepoName] `` prefix from all matching titles.
    2. If stripping creates duplicate titles within the same org,
       keep the newest (MAX id), deactivate the rest.
    """
    # Step 1: Strip [RepoName] prefix
    op.execute(
        """
        UPDATE knowledge_items
        SET title = regexp_replace(title, '^\\[[^\\]]+\\]\\s*', '')
        WHERE category = 'feature_registry'
          AND title ~ '^\\[[^\\]]+\\]'
        """
    )

    # Step 2: Deactivate duplicates created by prefix stripping.
    # For each (org_id, title) group with more than one active item,
    # keep the one with the latest created_at and deactivate the rest.
    op.execute(
        """
        UPDATE knowledge_items ki
        SET is_active = false, embedding = null
        FROM (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY org_id, title
                           ORDER BY created_at DESC
                       ) AS rn
                FROM knowledge_items
                WHERE category = 'feature_registry'
                  AND is_active = true
            ) ranked
            WHERE rn > 1
        ) dupes
        WHERE ki.id = dupes.id
        """
    )


def downgrade() -> None:
    """No-op: cannot reconstruct original repo prefixes."""
    pass
