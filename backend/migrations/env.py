import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.shared.config.settings import get_settings
from src.shared.infrastructure.db.base import Base

# Import every module's ORM models so Base.metadata is fully populated for
# autogenerate. One line per module, per Phase 9's module-registration idea.
import src.modules.accounting.infrastructure.models  # noqa: F401,E402
import src.modules.identity.infrastructure.master_data_models  # noqa: F401,E402
import src.modules.identity.infrastructure.models  # noqa: F401,E402
import src.modules.inventory.infrastructure.models  # noqa: F401,E402
import src.modules.purchasing.infrastructure.models  # noqa: F401,E402
import src.modules.sales.infrastructure.models  # noqa: F401,E402

config = context.config
settings = get_settings()
# Phase 17C-RLS: prefer the migration-role connection string; only fall
# back to database_url_sync (the runtime role, in the new architecture)
# for local developer convenience when DATABASE_URL_MIGRATE_SYNC isn't
# set. Production must always set DATABASE_URL_MIGRATE_SYNC explicitly —
# this fallback existing is not a substitute for that.
migration_url = settings.database_url_migrate_sync or settings.database_url_sync
config.set_main_option("sqlalchemy.url", migration_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
