"""Project-scoped memory and conversations."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project", sa.String(80), nullable=False),
        sa.Column("session", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created", sa.String(40), nullable=False),
    )
    op.create_index("ix_records_project", "records", ["project"])


def downgrade():
    op.drop_table("records")
