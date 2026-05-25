"""add user table and user_id to profile

Revision ID: add_user_auth_001
Revises: b3c4d5e6f7a8
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_user_auth_001'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('email', sa.String, nullable=False, unique=True),
        sa.Column('password_hash', sa.String, nullable=False),
        sa.Column('name', sa.String, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    # SQLite: add column without FK constraint (not supported in ALTER)
    op.add_column('profile', sa.Column('user_id', sa.Integer, nullable=True))
    op.create_index('ix_profile_user_id', 'profile', ['user_id'])
    op.create_index('ix_user_email', 'user', ['email'])


def downgrade() -> None:
    op.drop_index('ix_profile_user_id', 'profile')
    op.drop_column('profile', 'user_id')
    op.drop_index('ix_user_email', 'user')
    op.drop_table('user')
