"""Add session metadata columns and job_result_id to generated_cv

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7a8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    # Richer metadata on each scan session
    op.add_column('auto_apply_session', sa.Column('search_keyword', sa.String(), nullable=True))
    op.add_column('auto_apply_session', sa.Column('location', sa.String(), nullable=True))
    op.add_column('auto_apply_session', sa.Column('source', sa.String(), nullable=True, server_default='linkedin'))
    op.add_column('auto_apply_session', sa.Column('filters_json', sa.Text(), nullable=True))

    # Link generated CVs back to the job result so we can track resume versions
    op.add_column('generated_cv', sa.Column('job_result_id', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('generated_cv', 'job_result_id')
    op.drop_column('auto_apply_session', 'filters_json')
    op.drop_column('auto_apply_session', 'source')
    op.drop_column('auto_apply_session', 'location')
    op.drop_column('auto_apply_session', 'search_keyword')
