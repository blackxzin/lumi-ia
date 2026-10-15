"""add persistent exercises and spaced review state"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project", sa.String(length=80), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("topic", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created", sa.String(length=40), nullable=False),
        sa.Column("updated", sa.String(length=40), nullable=False),
        sa.Column("next_review", sa.String(length=40), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ease", sa.String(length=20), nullable=False, server_default="2.5"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_rating", sa.Integer(), nullable=True),
    )
    op.create_index("ix_exercises_project", "exercises", ["project"])


def downgrade() -> None:
    op.drop_index("ix_exercises_project", table_name="exercises")
    op.drop_table("exercises")
