"""add match_score and fit_analysis to generated_cv

Revision ID: b2c3d4e5f6a7
Revises: f2a3b4c5d6e7
Create Date: 2026-05-20 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(generated_cv)")).fetchall()]
    if "match_score" not in cols:
        op.add_column("generated_cv", sa.Column("match_score", sa.Integer(), nullable=True))
    if "fit_analysis" not in cols:
        op.add_column("generated_cv", sa.Column("fit_analysis", sa.Text(), nullable=True))


def downgrade() -> None:
    pass
