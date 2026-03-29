"""backfill legacy blank account scope

Revision ID: 0007_backfill_legacy_scope
Revises: 0006_snapshot_llm_scope
Create Date: 2026-03-29 12:05:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_backfill_legacy_scope"
down_revision: Union[str, None] = "0006_snapshot_llm_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _resolve_target_account_id(bind) -> str | None:
    target_account_id = bind.execute(
        sa.text(
            """
            select id
            from trading_accounts
            where account_code = 'DEFAULT-001'
            order by created_at asc nulls last, id asc
            limit 1
            """
        )
    ).scalar()
    if target_account_id:
        return str(target_account_id)

    fallback_account_id = bind.execute(
        sa.text(
            """
            select id
            from trading_accounts
            order by created_at asc nulls last, id asc
            limit 1
            """
        )
    ).scalar()
    if fallback_account_id:
        return str(fallback_account_id)
    return None


def upgrade() -> None:
    bind = op.get_bind()
    target_account_id = _resolve_target_account_id(bind)
    if not target_account_id:
        return

    bind.execute(
        sa.text(
            """
            delete from review_snapshots legacy
            using review_snapshots scoped
            where legacy.account_id = ''
              and legacy.snapshot_type <> 'pool_market'
              and scoped.account_id = :target_account_id
              and scoped.trade_date = legacy.trade_date
              and scoped.snapshot_type = legacy.snapshot_type
              and scoped.ts_code = legacy.ts_code
            """
        ),
        {"target_account_id": target_account_id},
    )
    bind.execute(
        sa.text(
            """
            update review_snapshots
            set account_id = :target_account_id
            where account_id = ''
              and snapshot_type <> 'pool_market'
            """
        ),
        {"target_account_id": target_account_id},
    )

    bind.execute(
        sa.text(
            """
            delete from stock_pool_snapshots legacy
            using stock_pool_snapshots scoped
            where legacy.account_id = ''
              and scoped.account_id = :target_account_id
              and scoped.trade_date = legacy.trade_date
              and scoped.candidate_limit = legacy.candidate_limit
            """
        ),
        {"target_account_id": target_account_id},
    )
    bind.execute(
        sa.text(
            """
            update stock_pool_snapshots
            set account_id = :target_account_id
            where account_id = ''
            """
        ),
        {"target_account_id": target_account_id},
    )

    bind.execute(
        sa.text(
            """
            update llm_cache_entries
            set account_id = :target_account_id
            where account_id = ''
            """
        ),
        {"target_account_id": target_account_id},
    )
    bind.execute(
        sa.text(
            """
            update llm_call_logs
            set account_id = :target_account_id
            where account_id = ''
            """
        ),
        {"target_account_id": target_account_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    target_account_id = _resolve_target_account_id(bind)
    if not target_account_id:
        return

    bind.execute(
        sa.text(
            """
            update review_snapshots
            set account_id = ''
            where account_id = :target_account_id
              and snapshot_type <> 'pool_market'
            """
        ),
        {"target_account_id": target_account_id},
    )
    bind.execute(
        sa.text(
            """
            update stock_pool_snapshots
            set account_id = ''
            where account_id = :target_account_id
            """
        ),
        {"target_account_id": target_account_id},
    )
    bind.execute(
        sa.text(
            """
            update llm_cache_entries
            set account_id = ''
            where account_id = :target_account_id
            """
        ),
        {"target_account_id": target_account_id},
    )
    bind.execute(
        sa.text(
            """
            update llm_call_logs
            set account_id = ''
            where account_id = :target_account_id
            """
        ),
        {"target_account_id": target_account_id},
    )
