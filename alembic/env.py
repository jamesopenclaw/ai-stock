from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.database import Base

import app.models.account_config  # noqa: F401
import app.models.holding  # noqa: F401
import app.models.llm_cache_entry  # noqa: F401
import app.models.llm_call_log  # noqa: F401
import app.models.notification_event  # noqa: F401
import app.models.notification_setting  # noqa: F401
import app.models.notification_state_snapshot  # noqa: F401
import app.models.review_snapshot  # noqa: F401
import app.models.sector_scan_snapshot  # noqa: F401
import app.models.stock_pool_snapshot  # noqa: F401
import app.models.task_run  # noqa: F401
import app.models.ths_concept_index  # noqa: F401
import app.models.ths_concept_member  # noqa: F401
import app.models.ths_concept_sync_state  # noqa: F401
import app.models.account_setting  # noqa: F401
import app.models.trading_account  # noqa: F401
import app.models.user  # noqa: F401
import app.models.user_session  # noqa: F401


config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
