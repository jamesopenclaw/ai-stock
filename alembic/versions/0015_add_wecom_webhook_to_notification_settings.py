"""add wecom webhook url to notification settings

Revision ID: 0015_add_wecom_webhook
Revises: 0014_ths_sync_state
Create Date: 2026-04-11 23:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_add_wecom_webhook"
down_revision: Union[str, None] = "0014_ths_sync_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column("wecom_webhook_url", sa.String(length=500), nullable=False, server_default=""),
    )
    op.execute("UPDATE notification_settings SET wecom_webhook_url = '' WHERE wecom_webhook_url IS NULL")
    op.alter_column("notification_settings", "wecom_webhook_url", server_default=None)


def downgrade() -> None:
    op.drop_column("notification_settings", "wecom_webhook_url")
