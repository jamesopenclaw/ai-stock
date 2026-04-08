"""add ths concept cache tables

Revision ID: 0013_ths_concept_cache
Revises: 0012_add_notification_state_snapshots
Create Date: 2026-04-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_ths_concept_cache"
down_revision: Union[str, None] = "0012_notify_state_snap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ths_concept_index",
        sa.Column("ts_code", sa.String(length=20), nullable=False),
        sa.Column("concept_name", sa.String(length=120), nullable=False),
        sa.Column("ths_type", sa.String(length=10), nullable=False),
        sa.Column("exchange", sa.String(length=10), nullable=False),
        sa.Column("sync_trade_date", sa.String(length=20), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("ts_code"),
    )
    op.create_index("ix_ths_concept_index_synced_at", "ths_concept_index", ["synced_at"], unique=False)
    op.create_index("ix_ths_concept_index_updated_at", "ths_concept_index", ["updated_at"], unique=False)

    op.create_table(
        "ths_concept_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("concept_code", sa.String(length=20), nullable=False),
        sa.Column("stock_code", sa.String(length=20), nullable=False),
        sa.Column("stock_name", sa.String(length=120), nullable=False),
        sa.Column("sync_trade_date", sa.String(length=20), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_code", "stock_code", name="uq_ths_concept_member_key"),
    )
    op.create_index("ix_ths_concept_members_concept_code", "ths_concept_members", ["concept_code"], unique=False)
    op.create_index("ix_ths_concept_members_stock_code", "ths_concept_members", ["stock_code"], unique=False)
    op.create_index("ix_ths_concept_members_sync_trade_date", "ths_concept_members", ["sync_trade_date"], unique=False)
    op.create_index("ix_ths_concept_members_synced_at", "ths_concept_members", ["synced_at"], unique=False)
    op.create_index("ix_ths_concept_members_updated_at", "ths_concept_members", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ths_concept_members_updated_at", table_name="ths_concept_members")
    op.drop_index("ix_ths_concept_members_synced_at", table_name="ths_concept_members")
    op.drop_index("ix_ths_concept_members_sync_trade_date", table_name="ths_concept_members")
    op.drop_index("ix_ths_concept_members_stock_code", table_name="ths_concept_members")
    op.drop_index("ix_ths_concept_members_concept_code", table_name="ths_concept_members")
    op.drop_table("ths_concept_members")

    op.drop_index("ix_ths_concept_index_updated_at", table_name="ths_concept_index")
    op.drop_index("ix_ths_concept_index_synced_at", table_name="ths_concept_index")
    op.drop_table("ths_concept_index")
