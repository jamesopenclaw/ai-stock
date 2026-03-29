"""add account scope to snapshots and llm tables

Revision ID: 0006_snapshot_llm_scope
Revises: 0005_add_account_id_to_holdings
Create Date: 2026-03-29 03:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_snapshot_llm_scope"
down_revision: Union[str, None] = "0005_add_account_id_to_holdings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "review_snapshots",
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index(op.f("ix_review_snapshots_account_id"), "review_snapshots", ["account_id"], unique=False)
    op.drop_constraint("uq_review_snapshot_key", "review_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_review_snapshot_key",
        "review_snapshots",
        ["trade_date", "snapshot_type", "ts_code", "account_id"],
    )

    op.add_column(
        "stock_pool_snapshots",
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index(op.f("ix_stock_pool_snapshots_account_id"), "stock_pool_snapshots", ["account_id"], unique=False)
    op.drop_constraint("uq_stock_pool_snapshot_key", "stock_pool_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_stock_pool_snapshot_key",
        "stock_pool_snapshots",
        ["trade_date", "candidate_limit", "account_id"],
    )

    op.add_column(
        "llm_cache_entries",
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index(op.f("ix_llm_cache_entries_account_id"), "llm_cache_entries", ["account_id"], unique=False)

    op.add_column(
        "llm_call_logs",
        sa.Column("account_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index(op.f("ix_llm_call_logs_account_id"), "llm_call_logs", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_call_logs_account_id"), table_name="llm_call_logs")
    op.drop_column("llm_call_logs", "account_id")

    op.drop_index(op.f("ix_llm_cache_entries_account_id"), table_name="llm_cache_entries")
    op.drop_column("llm_cache_entries", "account_id")

    op.drop_constraint("uq_stock_pool_snapshot_key", "stock_pool_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_stock_pool_snapshot_key",
        "stock_pool_snapshots",
        ["trade_date", "candidate_limit"],
    )
    op.drop_index(op.f("ix_stock_pool_snapshots_account_id"), table_name="stock_pool_snapshots")
    op.drop_column("stock_pool_snapshots", "account_id")

    op.drop_constraint("uq_review_snapshot_key", "review_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_review_snapshot_key",
        "review_snapshots",
        ["trade_date", "snapshot_type", "ts_code"],
    )
    op.drop_index(op.f("ix_review_snapshots_account_id"), table_name="review_snapshots")
    op.drop_column("review_snapshots", "account_id")
