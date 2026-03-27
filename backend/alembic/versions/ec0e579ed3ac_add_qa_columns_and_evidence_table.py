"""add_qa_columns_and_evidence_table

Revision ID: ec0e579ed3ac
Revises: a3f7b2c1d4e5
Create Date: 2026-03-28 01:08:30.504623

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ec0e579ed3ac'
down_revision: Union[str, None] = 'a3f7b2c1d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add QA columns to bud_documents
    op.add_column('bud_documents', sa.Column('qa_automation_cases', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('bud_documents', sa.Column('qa_manual_cases', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('bud_documents', sa.Column('qa_execution_plan_md', sa.Text(), nullable=True))

    # Create qa_test_evidence table
    op.create_table(
        'qa_test_evidence',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('bud_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('test_case_id', sa.String(20), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('storage_path', sa.String(1000), nullable=False),
        sa.Column('uploaded_by', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['bud_id'], ['bud_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_qa_test_evidence_org_id', 'qa_test_evidence', ['org_id'])
    op.create_index('ix_qa_test_evidence_bud_id', 'qa_test_evidence', ['bud_id'])
    op.create_index('ix_qa_test_evidence_test_case_id', 'qa_test_evidence', ['test_case_id'])


def downgrade() -> None:
    op.drop_index('ix_qa_test_evidence_test_case_id', table_name='qa_test_evidence')
    op.drop_index('ix_qa_test_evidence_bud_id', table_name='qa_test_evidence')
    op.drop_index('ix_qa_test_evidence_org_id', table_name='qa_test_evidence')
    op.drop_table('qa_test_evidence')
    op.drop_column('bud_documents', 'qa_execution_plan_md')
    op.drop_column('bud_documents', 'qa_manual_cases')
    op.drop_column('bud_documents', 'qa_automation_cases')
