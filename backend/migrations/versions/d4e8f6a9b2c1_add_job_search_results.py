"""add_job_search_results

Revision ID: d4e8f6a9b2c1
Revises: c3e7f9a12b04
Create Date: 2026-05-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e8f6a9b2c1'
down_revision: Union[str, Sequence[str], None] = 'c3e7f9a12b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'job_search_result',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('scan_url', sa.String(), nullable=True),
        sa.Column('company_name', sa.String(), nullable=True),
        sa.Column('role_title', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('salary', sa.String(), nullable=True),
        sa.Column('job_url', sa.String(), nullable=True),
        sa.Column('apply_url', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('easy_apply', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('posted_at', sa.String(), nullable=True),
        sa.Column('match_score', sa.Integer(), nullable=True),
        sa.Column('match_data', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('application_id', sa.Integer(), nullable=True),
        sa.Column('profile_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['application.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['profile_id'], ['profile.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('job_search_result')
