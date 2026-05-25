"""add apply_session table

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create apply_session table if it doesn't exist
    conn = op.get_bind()
    tables = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='apply_session'")
    ).fetchall()
    if not tables:
        op.create_table(
            "apply_session",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("session_key", sa.String, nullable=False, unique=True),
            sa.Column("profile_id", sa.Integer, sa.ForeignKey("profile.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String, nullable=False, server_default="in_progress"),
            sa.Column("job_url", sa.String, nullable=True),
            sa.Column("company_name", sa.String, nullable=True),
            sa.Column("role_title", sa.String, nullable=True),
            sa.Column("location", sa.String, nullable=True),
            sa.Column("salary", sa.String, nullable=True),
            sa.Column("job_description", sa.Text, nullable=True),
            sa.Column("match_score", sa.Integer, nullable=True),
            sa.Column("fit_analysis", sa.Text, nullable=True),
            sa.Column("config", sa.Text, nullable=True),
            sa.Column("application_id", sa.Integer, sa.ForeignKey("application.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.Column("updated_at", sa.DateTime, nullable=True),
        )


def downgrade() -> None:
    op.drop_table("apply_session")
