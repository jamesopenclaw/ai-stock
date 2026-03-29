"""create core tables

Revision ID: 0001_create_core_tables
Revises: 
Create Date: 2026-03-28 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_create_core_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("total_asset", sa.Float(), nullable=False),
        sa.Column("llm_enabled", sa.Boolean(), nullable=False),
        sa.Column("llm_provider", sa.String(length=40), nullable=False),
        sa.Column("llm_base_url", sa.String(length=255), nullable=False),
        sa.Column("llm_api_key", sa.String(length=255), nullable=False),
        sa.Column("llm_model", sa.String(length=120), nullable=False),
        sa.Column("llm_timeout_seconds", sa.Float(), nullable=False),
        sa.Column("llm_temperature", sa.Float(), nullable=False),
        sa.Column("llm_max_input_items", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "holdings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("ts_code", sa.String(), nullable=False),
        sa.Column("stock_name", sa.String(), nullable=True),
        sa.Column("holding_qty", sa.Integer(), nullable=False),
        sa.Column("cost_price", sa.Float(), nullable=False),
        sa.Column("market_price", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("holding_market_value", sa.Float(), nullable=True),
        sa.Column("buy_date", sa.String(), nullable=False),
        sa.Column("can_sell_today", sa.Boolean(), nullable=True),
        sa.Column("holding_reason", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_holdings_ts_code"), "holdings", ["ts_code"], unique=False)

    op.create_table(
        "llm_cache_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scene", sa.String(length=60), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("trade_date", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index(op.f("ix_llm_cache_entries_cache_key"), "llm_cache_entries", ["cache_key"], unique=True)
    op.create_index(op.f("ix_llm_cache_entries_created_at"), "llm_cache_entries", ["created_at"], unique=False)
    op.create_index(op.f("ix_llm_cache_entries_scene"), "llm_cache_entries", ["scene"], unique=False)
    op.create_index(op.f("ix_llm_cache_entries_trade_date"), "llm_cache_entries", ["trade_date"], unique=False)
    op.create_index(op.f("ix_llm_cache_entries_updated_at"), "llm_cache_entries", ["updated_at"], unique=False)

    op.create_table(
        "llm_call_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scene", sa.String(length=60), nullable=False),
        sa.Column("trade_date", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("request_chars", sa.Integer(), nullable=False),
        sa.Column("response_chars", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_call_logs_created_at"), "llm_call_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_scene"), "llm_call_logs", ["scene"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_status"), "llm_call_logs", ["status"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_success"), "llm_call_logs", ["success"], unique=False)
    op.create_index(op.f("ix_llm_call_logs_trade_date"), "llm_call_logs", ["trade_date"], unique=False)

    op.create_table(
        "review_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.String(), nullable=False),
        sa.Column("snapshot_type", sa.String(), nullable=False),
        sa.Column("ts_code", sa.String(), nullable=False),
        sa.Column("stock_name", sa.String(), nullable=False),
        sa.Column("candidate_source_tag", sa.String(), nullable=True),
        sa.Column("candidate_bucket_tag", sa.String(), nullable=True),
        sa.Column("buy_signal_tag", sa.String(), nullable=True),
        sa.Column("buy_point_type", sa.String(), nullable=True),
        sa.Column("stock_pool_tag", sa.String(), nullable=True),
        sa.Column("stock_score", sa.Float(), nullable=True),
        sa.Column("base_price", sa.Float(), nullable=True),
        sa.Column("return_1d", sa.Float(), nullable=True),
        sa.Column("return_3d", sa.Float(), nullable=True),
        sa.Column("return_5d", sa.Float(), nullable=True),
        sa.Column("resolved_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_date", "snapshot_type", "ts_code", name="uq_review_snapshot_key"),
    )
    op.create_index(op.f("ix_review_snapshots_snapshot_type"), "review_snapshots", ["snapshot_type"], unique=False)
    op.create_index(op.f("ix_review_snapshots_trade_date"), "review_snapshots", ["trade_date"], unique=False)
    op.create_index(op.f("ix_review_snapshots_ts_code"), "review_snapshots", ["ts_code"], unique=False)

    op.create_table(
        "sector_scan_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.String(), nullable=False),
        sa.Column("resolved_trade_date", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_date", name="uq_sector_scan_snapshot_trade_date"),
    )
    op.create_index(op.f("ix_sector_scan_snapshots_trade_date"), "sector_scan_snapshots", ["trade_date"], unique=False)

    op.create_table(
        "stock_pool_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.String(), nullable=False),
        sa.Column("candidate_limit", sa.Integer(), nullable=False),
        sa.Column("resolved_trade_date", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_date", "candidate_limit", name="uq_stock_pool_snapshot_key"),
    )
    op.create_index(op.f("ix_stock_pool_snapshots_candidate_limit"), "stock_pool_snapshots", ["candidate_limit"], unique=False)
    op.create_index(op.f("ix_stock_pool_snapshots_trade_date"), "stock_pool_snapshots", ["trade_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_pool_snapshots_trade_date"), table_name="stock_pool_snapshots")
    op.drop_index(op.f("ix_stock_pool_snapshots_candidate_limit"), table_name="stock_pool_snapshots")
    op.drop_table("stock_pool_snapshots")

    op.drop_index(op.f("ix_sector_scan_snapshots_trade_date"), table_name="sector_scan_snapshots")
    op.drop_table("sector_scan_snapshots")

    op.drop_index(op.f("ix_review_snapshots_ts_code"), table_name="review_snapshots")
    op.drop_index(op.f("ix_review_snapshots_trade_date"), table_name="review_snapshots")
    op.drop_index(op.f("ix_review_snapshots_snapshot_type"), table_name="review_snapshots")
    op.drop_table("review_snapshots")

    op.drop_index(op.f("ix_llm_call_logs_trade_date"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_success"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_status"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_scene"), table_name="llm_call_logs")
    op.drop_index(op.f("ix_llm_call_logs_created_at"), table_name="llm_call_logs")
    op.drop_table("llm_call_logs")

    op.drop_index(op.f("ix_llm_cache_entries_updated_at"), table_name="llm_cache_entries")
    op.drop_index(op.f("ix_llm_cache_entries_trade_date"), table_name="llm_cache_entries")
    op.drop_index(op.f("ix_llm_cache_entries_scene"), table_name="llm_cache_entries")
    op.drop_index(op.f("ix_llm_cache_entries_created_at"), table_name="llm_cache_entries")
    op.drop_index(op.f("ix_llm_cache_entries_cache_key"), table_name="llm_cache_entries")
    op.drop_table("llm_cache_entries")

    op.drop_index(op.f("ix_holdings_ts_code"), table_name="holdings")
    op.drop_table("holdings")

    op.drop_table("account_config")
