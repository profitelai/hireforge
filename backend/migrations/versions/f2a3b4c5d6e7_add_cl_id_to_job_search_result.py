"""add cl_id to job_search_result

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-20 06:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(job_search_result)"))]
    if 'cl_id' not in cols:
        op.add_column(
            'job_search_result',
            sa.Column('cl_id', sa.Integer(), sa.ForeignKey('generated_cover_letter.id', ondelete='SET NULL'), nullable=True),
        )


def downgrade() -> None:
    op.drop_column('job_search_result', 'cl_id')
