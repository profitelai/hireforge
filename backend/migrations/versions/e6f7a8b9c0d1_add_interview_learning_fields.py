"""add answer_length to interview_session and grammar_errors/improved_answer to interview_question

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def _col_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()

    if not _col_exists(conn, "interview_session", "answer_length"):
        op.add_column("interview_session", sa.Column("answer_length", sa.String(), nullable=True))

    if not _col_exists(conn, "interview_question", "grammar_errors"):
        op.add_column("interview_question", sa.Column("grammar_errors", sa.Text(), nullable=True))

    if not _col_exists(conn, "interview_question", "improved_answer"):
        op.add_column("interview_question", sa.Column("improved_answer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("interview_question", "improved_answer")
    op.drop_column("interview_question", "grammar_errors")
    op.drop_column("interview_session", "answer_length")
