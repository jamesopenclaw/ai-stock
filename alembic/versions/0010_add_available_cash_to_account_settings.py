"""add available cash to account settings

Revision ID: 0010_add_available_cash
Revises: 0009_snapshot_addpos
Create Date: 2026-04-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_add_available_cash"
down_revision: Union[str, None] = "0009_snapshot_addpos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("account_settings", sa.Column("available_cash", sa.Float(), nullable=True))
    op.execute("UPDATE account_settings SET available_cash = total_asset WHERE available_cash IS NULL")


def downgrade() -> None:
    op.drop_column("account_settings", "available_cash")
