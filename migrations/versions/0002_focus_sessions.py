"""Persist completed focus sessions for learning progress."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project", sa.String(80), nullable=False),
        sa.Column("goal", sa.String(240), nullable=False),
        sa.Column("focus_minutes", sa.Integer(), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started", sa.String(40), nullable=False),
        sa.Column("ended", sa.String(40), nullable=False),
    )
    op.create_index("ix_focus_sessions_project", "focus_sessions", ["project"])


def downgrade():
    op.drop_table("focus_sessions")
