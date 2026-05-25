"""add cv_id to job_search_result

Revision ID: e1f2a3b4c5d6
Revises: d4e8f6a9b2c1
Create Date: 2026-05-20 05:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd4e8f6a9b2c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(job_search_result)"))]
    if 'cv_id' not in cols:
        op.add_column(
            'job_search_result',
            sa.Column('cv_id', sa.Integer(), sa.ForeignKey('generated_cv.id', ondelete='SET NULL'), nullable=True),
        )


def downgrade() -> None:
    op.drop_column('job_search_result', 'cv_id')
