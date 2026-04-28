"""add task table and efficiency columns

Revision ID: a1b2c3d4e5f6
Revises: f305a74ff842
Create Date: 2026-04-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f305a74ff842"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create task table
    op.create_table(
        "task",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("task_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("start_turn", sa.Integer(), nullable=False),
        sa.Column("end_turn", sa.Integer(), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context_at_start", sa.Integer(), nullable=True),
        sa.Column("estimated_waste_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["coding_session.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_tenant_id"), "task", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_task_session_id"), "task", ["session_id"], unique=False)

    # Add efficiency columns to coding_session
    with op.batch_alter_table("coding_session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("compaction_cycle_waste", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("floor_drift_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("interrupted_turn_waste", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("repeated_edit_waste", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("failed_retry_waste", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("efficiency_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("task_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("estimated_task_waste_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("coding_session", schema=None) as batch_op:
        batch_op.drop_column("estimated_task_waste_tokens")
        batch_op.drop_column("task_count")
        batch_op.drop_column("efficiency_score")
        batch_op.drop_column("failed_retry_waste")
        batch_op.drop_column("repeated_edit_waste")
        batch_op.drop_column("interrupted_turn_waste")
        batch_op.drop_column("floor_drift_score")
        batch_op.drop_column("compaction_cycle_waste")

    op.drop_index(op.f("ix_task_session_id"), table_name="task")
    op.drop_index(op.f("ix_task_tenant_id"), table_name="task")
    op.drop_table("task")
