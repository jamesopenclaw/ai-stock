"""drop llm columns from account settings

Revision ID: 0008_drop_account_setting_llm
Revises: 0007_backfill_legacy_scope
Create Date: 2026-03-29 14:05:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_drop_account_setting_llm"
down_revision: Union[str, None] = "0007_backfill_legacy_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("account_settings", "llm_max_input_items")
    op.drop_column("account_settings", "llm_temperature")
    op.drop_column("account_settings", "llm_timeout_seconds")
    op.drop_column("account_settings", "llm_model")
    op.drop_column("account_settings", "llm_api_key")
    op.drop_column("account_settings", "llm_base_url")
    op.drop_column("account_settings", "llm_provider")
    op.drop_column("account_settings", "llm_enabled")


def downgrade() -> None:
    op.add_column(
        "account_settings",
        sa.Column("llm_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "account_settings",
        sa.Column("llm_provider", sa.String(length=40), nullable=False, server_default="custom"),
    )
    op.add_column(
        "account_settings",
        sa.Column("llm_base_url", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "account_settings",
        sa.Column("llm_api_key", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "account_settings",
        sa.Column("llm_model", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column(
        "account_settings",
        sa.Column("llm_timeout_seconds", sa.Float(), nullable=False, server_default="60"),
    )
    op.add_column(
        "account_settings",
        sa.Column("llm_temperature", sa.Float(), nullable=False, server_default="0.2"),
    )
    op.add_column(
        "account_settings",
        sa.Column("llm_max_input_items", sa.Integer(), nullable=False, server_default="8"),
    )
