"""add add-position fields to review snapshots

Revision ID: 0009_snapshot_addpos
Revises: 0008_drop_account_setting_llm
Create Date: 2026-03-31 10:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_snapshot_addpos"
down_revision: Union[str, None] = "0008_drop_account_setting_llm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "review_snapshots",
        sa.Column("trade_mode", sa.String(length=32), nullable=False, server_default=""),
    )
    op.add_column(
        "review_snapshots",
        sa.Column("add_position_decision", sa.String(length=32), nullable=False, server_default=""),
    )
    op.add_column(
        "review_snapshots",
        sa.Column("add_position_score_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "review_snapshots",
        sa.Column("add_position_scene", sa.String(length=32), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("review_snapshots", "add_position_scene")
    op.drop_column("review_snapshots", "add_position_score_total")
    op.drop_column("review_snapshots", "add_position_decision")
    op.drop_column("review_snapshots", "trade_mode")
