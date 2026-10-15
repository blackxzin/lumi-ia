"""Add usage metrics and focus reflections."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("focus_sessions") as batch:
        batch.add_column(sa.Column("outcome", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("next_step", sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project", sa.String(80), nullable=False),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("value", sa.String(200), nullable=False, server_default=""),
        sa.Column("created", sa.String(40), nullable=False),
    )
    op.create_index("ix_metrics_project", "metrics", ["project"])


def downgrade() -> None:
    op.drop_index("ix_metrics_project", table_name="metrics")
    op.drop_table("metrics")
    with op.batch_alter_table("focus_sessions") as batch:
        batch.drop_column("next_step")
        batch.drop_column("outcome")
