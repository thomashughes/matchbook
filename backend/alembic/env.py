"""
Alembic migration entrypoint.

This runs under sync Python (Alembic itself is synchronous), so we use
the DATABASE_URL_SYNC (psycopg2) variant. The app runtime still uses the
async DATABASE_URL (asyncpg).

target_metadata is taken from our ORM's Base, so `alembic revision
--autogenerate` can diff the live DB against the declared models.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure Alembic picks up ALL models by importing the package — the
# models/__init__.py re-exports each class so SQLAlchemy's metadata is
# fully populated before autogenerate runs.
from app import models  # noqa: F401
from app.core.config import get_settings
from app.models.base import Base

config = context.config

# Feed the sync URL from our settings into Alembic at runtime so we
# don't duplicate it in alembic.ini (which would inevitably drift).
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL_SYNC)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without a DB connection — used for generating SQL scripts."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # compare_type catches column-type changes (e.g. VARCHAR(255) -> TEXT)
        # that naive autogenerate would otherwise miss.
        compare_type=True,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
