"""persist focus task steps"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "focus_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project", sa.String(length=80), nullable=False),
        sa.Column("goal", sa.String(length=240), nullable=False),
        sa.Column("steps", sa.Text(), nullable=False),
        sa.Column("updated", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("project", "goal", name="uq_focus_plans_project_goal"),
    )
    op.create_index("ix_focus_plans_project", "focus_plans", ["project"])


def downgrade() -> None:
    op.drop_index("ix_focus_plans_project", table_name="focus_plans")
    op.drop_table("focus_plans")
