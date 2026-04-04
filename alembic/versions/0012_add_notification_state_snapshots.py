"""add notification state snapshots

Revision ID: 0012_notify_state_snap
Revises: 0011_add_notification_tables
Create Date: 2026-04-04 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_notify_state_snap"
down_revision: Union[str, None] = "0011_add_notification_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_state_snapshots",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("state_type", sa.String(length=40), nullable=False),
        sa.Column("state_key", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_code", sa.String(length=40), nullable=True),
        sa.Column("current_value", sa.String(length=40), nullable=False),
        sa.Column("current_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_trade_date", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("state_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_state_snapshots_account_id",
        "notification_state_snapshots",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_state_snapshots_state_type",
        "notification_state_snapshots",
        ["state_type"],
        unique=False,
    )
    op.create_index(
        "ix_notification_state_snapshots_entity_code",
        "notification_state_snapshots",
        ["entity_code"],
        unique=False,
    )
    op.create_index(
        "ix_notification_state_snapshots_last_trade_date",
        "notification_state_snapshots",
        ["last_trade_date"],
        unique=False,
    )
    op.create_index(
        "ix_notification_state_snapshots_created_at",
        "notification_state_snapshots",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_state_snapshots_updated_at",
        "notification_state_snapshots",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_state_snapshots_account_type",
        "notification_state_snapshots",
        ["account_id", "state_type"],
        unique=False,
    )
    op.create_index(
        "ix_notification_state_snapshots_account_key",
        "notification_state_snapshots",
        ["account_id", "state_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_state_snapshots_account_key", table_name="notification_state_snapshots")
    op.drop_index("ix_notification_state_snapshots_account_type", table_name="notification_state_snapshots")
    op.drop_index("ix_notification_state_snapshots_updated_at", table_name="notification_state_snapshots")
    op.drop_index("ix_notification_state_snapshots_created_at", table_name="notification_state_snapshots")
    op.drop_index("ix_notification_state_snapshots_last_trade_date", table_name="notification_state_snapshots")
    op.drop_index("ix_notification_state_snapshots_entity_code", table_name="notification_state_snapshots")
    op.drop_index("ix_notification_state_snapshots_state_type", table_name="notification_state_snapshots")
    op.drop_index("ix_notification_state_snapshots_account_id", table_name="notification_state_snapshots")
    op.drop_table("notification_state_snapshots")
