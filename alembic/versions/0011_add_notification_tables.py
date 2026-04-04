"""add notification tables

Revision ID: 0011_add_notification_tables
Revises: 0010_add_available_cash
Create Date: 2026-04-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_add_notification_tables"
down_revision: Union[str, None] = "0010_add_available_cash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_events",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("action_label", sa.String(length=60), nullable=False),
        sa.Column("action_target_type", sa.String(length=30), nullable=False),
        sa.Column("action_target_payload", sa.JSON(), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_code", sa.String(length=40), nullable=True),
        sa.Column("trade_date", sa.String(length=20), nullable=False),
        sa.Column("data_source", sa.String(length=40), nullable=True),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("trigger_value", sa.JSON(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_events_account_id", "notification_events", ["account_id"], unique=False)
    op.create_index("ix_notification_events_user_id", "notification_events", ["user_id"], unique=False)
    op.create_index("ix_notification_events_event_type", "notification_events", ["event_type"], unique=False)
    op.create_index("ix_notification_events_category", "notification_events", ["category"], unique=False)
    op.create_index("ix_notification_events_priority", "notification_events", ["priority"], unique=False)
    op.create_index("ix_notification_events_status", "notification_events", ["status"], unique=False)
    op.create_index("ix_notification_events_entity_code", "notification_events", ["entity_code"], unique=False)
    op.create_index("ix_notification_events_trade_date", "notification_events", ["trade_date"], unique=False)
    op.create_index("ix_notification_events_created_at", "notification_events", ["created_at"], unique=False)
    op.create_index("ix_notification_events_updated_at", "notification_events", ["updated_at"], unique=False)
    op.create_index(
        "ix_notification_events_account_status_created",
        "notification_events",
        ["account_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_events_account_priority_created",
        "notification_events",
        ["account_id", "priority", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_events_account_dedupe",
        "notification_events",
        ["account_id", "dedupe_key"],
        unique=True,
    )

    op.create_table(
        "notification_settings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("wecom_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("quiet_windows", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_settings_account_id", "notification_settings", ["account_id"], unique=False)
    op.create_index("ix_notification_settings_user_id", "notification_settings", ["user_id"], unique=False)
    op.create_index("ix_notification_settings_created_at", "notification_settings", ["created_at"], unique=False)
    op.create_index("ix_notification_settings_updated_at", "notification_settings", ["updated_at"], unique=False)
    op.create_index(
        "ix_notification_settings_account_unique",
        "notification_settings",
        ["account_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_settings_account_unique", table_name="notification_settings")
    op.drop_index("ix_notification_settings_updated_at", table_name="notification_settings")
    op.drop_index("ix_notification_settings_created_at", table_name="notification_settings")
    op.drop_index("ix_notification_settings_user_id", table_name="notification_settings")
    op.drop_index("ix_notification_settings_account_id", table_name="notification_settings")
    op.drop_table("notification_settings")

    op.drop_index("ix_notification_events_account_dedupe", table_name="notification_events")
    op.drop_index("ix_notification_events_account_priority_created", table_name="notification_events")
    op.drop_index("ix_notification_events_account_status_created", table_name="notification_events")
    op.drop_index("ix_notification_events_updated_at", table_name="notification_events")
    op.drop_index("ix_notification_events_created_at", table_name="notification_events")
    op.drop_index("ix_notification_events_trade_date", table_name="notification_events")
    op.drop_index("ix_notification_events_entity_code", table_name="notification_events")
    op.drop_index("ix_notification_events_status", table_name="notification_events")
    op.drop_index("ix_notification_events_priority", table_name="notification_events")
    op.drop_index("ix_notification_events_category", table_name="notification_events")
    op.drop_index("ix_notification_events_event_type", table_name="notification_events")
    op.drop_index("ix_notification_events_user_id", table_name="notification_events")
    op.drop_index("ix_notification_events_account_id", table_name="notification_events")
    op.drop_table("notification_events")
