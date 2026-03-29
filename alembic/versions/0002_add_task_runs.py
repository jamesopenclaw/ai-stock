"""add task runs

Revision ID: 0002_add_task_runs
Revises: 0001_create_core_tables
Create Date: 2026-03-28 00:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_task_runs"
down_revision: Union[str, None] = "0001_create_core_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_runs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("trade_date", sa.String(length=20), nullable=False),
        sa.Column("trigger_source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_runs_created_at"), "task_runs", ["created_at"], unique=False)
    op.create_index(op.f("ix_task_runs_mode"), "task_runs", ["mode"], unique=False)
    op.create_index(op.f("ix_task_runs_status"), "task_runs", ["status"], unique=False)
    op.create_index(op.f("ix_task_runs_trade_date"), "task_runs", ["trade_date"], unique=False)
    op.create_index(op.f("ix_task_runs_updated_at"), "task_runs", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_task_runs_updated_at"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_trade_date"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_status"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_mode"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_created_at"), table_name="task_runs")
    op.drop_table("task_runs")
