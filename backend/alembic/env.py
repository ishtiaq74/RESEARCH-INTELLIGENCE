"""Alembic migration environment configuration."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.config import Settings
from app.db.session import create_db_engine

# Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata (none for MVP scaffold)
target_metadata = None


def get_url() -> str:
    """Return database URL from config or runtime app Settings."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return Settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and enables SQLite batch mode.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the migration context.
    Enables SQLite batch mode.
    """
    connection_override = config.attributes.get("connection", None)
    if connection_override is not None:
        context.configure(
            connection=connection_override,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    url = get_url()
    connectable = create_db_engine(url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
