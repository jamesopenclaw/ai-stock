"""add trading accounts

Revision ID: 0004_add_trading_accounts
Revises: 0003_add_auth_tables
Create Date: 2026-03-29 00:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_trading_accounts"
down_revision: Union[str, None] = "0003_add_auth_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("default_account_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_users_default_account_id"), "users", ["default_account_id"], unique=False)

    op.create_table(
        "trading_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_code", sa.String(length=64), nullable=False),
        sa.Column("account_name", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_code"),
    )
    op.create_index(op.f("ix_trading_accounts_account_code"), "trading_accounts", ["account_code"], unique=True)
    op.create_index(op.f("ix_trading_accounts_created_at"), "trading_accounts", ["created_at"], unique=False)
    op.create_index(op.f("ix_trading_accounts_owner_user_id"), "trading_accounts", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_trading_accounts_status"), "trading_accounts", ["status"], unique=False)
    op.create_index(op.f("ix_trading_accounts_updated_at"), "trading_accounts", ["updated_at"], unique=False)

    op.create_table(
        "account_settings",
        sa.Column("account_id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"]),
        sa.PrimaryKeyConstraint("account_id"),
    )


def downgrade() -> None:
    op.drop_table("account_settings")

    op.drop_index(op.f("ix_trading_accounts_updated_at"), table_name="trading_accounts")
    op.drop_index(op.f("ix_trading_accounts_status"), table_name="trading_accounts")
    op.drop_index(op.f("ix_trading_accounts_owner_user_id"), table_name="trading_accounts")
    op.drop_index(op.f("ix_trading_accounts_created_at"), table_name="trading_accounts")
    op.drop_index(op.f("ix_trading_accounts_account_code"), table_name="trading_accounts")
    op.drop_table("trading_accounts")

    op.drop_index(op.f("ix_users_default_account_id"), table_name="users")
    op.drop_column("users", "default_account_id")
