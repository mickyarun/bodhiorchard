"""mcp_audit_log: add params jsonb

Adds a JSONB ``params`` column so the audit log can record WHAT was
searched / requested per MCP call, not just which tool was called.
The handler-side ``_sanitise_params`` in ``app/mcp/audit.py`` filters
the dict against an allowlist before writing — never store free-form
blobs that could carry plaintext secrets.

Revision ID: af34446bb2fe
Revises: 2e830531ddcf
Create Date: 2026-05-21 08:46:49.327470

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "af34446bb2fe"
down_revision: str | None = "2e830531ddcf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_audit_log",
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mcp_audit_log", "params")
