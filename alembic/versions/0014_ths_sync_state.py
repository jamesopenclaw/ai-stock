"""add ths sync state table

Revision ID: 0014_ths_sync_state
Revises: 0013_ths_concept_cache
Create Date: 2026-04-08 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_ths_sync_state"
down_revision: Union[str, None] = "0013_ths_concept_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ths_concept_sync_states",
        sa.Column("sync_key", sa.String(length=40), nullable=False),
        sa.Column("target_trade_date", sa.String(length=20), nullable=False),
        sa.Column("active_trade_date", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_concepts", sa.Integer(), nullable=False),
        sa.Column("processed_concepts", sa.Integer(), nullable=False),
        sa.Column("next_cursor", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("sync_key"),
    )
    op.create_index("ix_ths_concept_sync_states_target_trade_date", "ths_concept_sync_states", ["target_trade_date"], unique=False)
    op.create_index("ix_ths_concept_sync_states_active_trade_date", "ths_concept_sync_states", ["active_trade_date"], unique=False)
    op.create_index("ix_ths_concept_sync_states_status", "ths_concept_sync_states", ["status"], unique=False)
    op.create_index("ix_ths_concept_sync_states_updated_at", "ths_concept_sync_states", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ths_concept_sync_states_updated_at", table_name="ths_concept_sync_states")
    op.drop_index("ix_ths_concept_sync_states_status", table_name="ths_concept_sync_states")
    op.drop_index("ix_ths_concept_sync_states_active_trade_date", table_name="ths_concept_sync_states")
    op.drop_index("ix_ths_concept_sync_states_target_trade_date", table_name="ths_concept_sync_states")
    op.drop_table("ths_concept_sync_states")
