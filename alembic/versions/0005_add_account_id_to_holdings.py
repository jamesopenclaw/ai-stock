"""add account id to holdings

Revision ID: 0005_add_account_id_to_holdings
Revises: 0004_add_trading_accounts
Create Date: 2026-03-29 01:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_account_id_to_holdings"
down_revision: Union[str, None] = "0004_add_trading_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("holdings", sa.Column("account_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_holdings_account_id"), "holdings", ["account_id"], unique=False)

    op.execute(
        """
        UPDATE holdings
        SET account_id = (
            SELECT id
            FROM trading_accounts
            ORDER BY created_at ASC NULLS LAST, id ASC
            LIMIT 1
        )
        WHERE account_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_holdings_account_id"), table_name="holdings")
    op.drop_column("holdings", "account_id")
