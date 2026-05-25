"""add resume_url to application

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-05-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(application)"))]
    if 'resume_url' not in cols:
        op.add_column('application', sa.Column('resume_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('application', 'resume_url')
