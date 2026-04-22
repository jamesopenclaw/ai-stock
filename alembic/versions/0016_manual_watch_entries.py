"""manual watch entries per trading account

Revision ID: 0016_manual_watch_entries
Revises: 0015_add_wecom_webhook
Create Date: 2026-04-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_manual_watch_entries"
down_revision: Union[str, None] = "0015_add_wecom_webhook"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manual_watch_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("ts_code", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "ts_code", name="uq_manual_watch_account_ts_code"),
    )
    op.create_index(op.f("ix_manual_watch_entries_account_id"), "manual_watch_entries", ["account_id"], unique=False)
    op.create_index(op.f("ix_manual_watch_entries_ts_code"), "manual_watch_entries", ["ts_code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_manual_watch_entries_ts_code"), table_name="manual_watch_entries")
    op.drop_index(op.f("ix_manual_watch_entries_account_id"), table_name="manual_watch_entries")
    op.drop_table("manual_watch_entries")
