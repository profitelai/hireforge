"""add language to generated_cv and generated_cover_letter

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-20 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    cv_cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(generated_cv)")).fetchall()]
    if "language" not in cv_cols:
        op.add_column("generated_cv", sa.Column("language", sa.String(), nullable=True, server_default="en"))

    cl_cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(generated_cover_letter)")).fetchall()]
    if "language" not in cl_cols:
        op.add_column("generated_cover_letter", sa.Column("language", sa.String(), nullable=True, server_default="en"))


def downgrade() -> None:
    pass
