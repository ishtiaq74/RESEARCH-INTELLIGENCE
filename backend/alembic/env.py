"""Alembic migration environment configuration.

Changes from T1 scaffold:
  - target_metadata now points to app.models.Base.metadata so Alembic can
    auto-detect schema changes.
  - Foreign key enforcement is DISABLED before running migrations and
    re-enabled (via PRAGMA foreign_key_check) afterwards.  This is required
    because SQLite batch mode rebuilds tables with CREATE TABLE / INSERT /
    DROP, which can trigger FK violations under PRAGMA foreign_keys=ON.
    (Documented in DECISIONS_LOG D-014.)
"""
from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from app.config import Settings
from app.db.session import create_db_engine

# Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so their tables are registered on Base.metadata.
# Alembic uses target_metadata to detect schema drift.
from app.models import Base  # noqa: E402

target_metadata = Base.metadata


def get_url() -> str:
    """Return database URL from config or runtime app Settings."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return Settings().database_url


def _configure_context(connection: Any, **kwargs: Any) -> None:
    """Apply shared context.configure options.

    render_as_batch=True is essential for SQLite: Alembic emulates ALTER TABLE
    by creating a new table, copying data, and dropping the old one.  Without
    it, any ALTER (add column, add FK) would fail on SQLite.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        **kwargs,
    )


def _disable_fk_and_run(connection: Any) -> None:
    """Disable FK enforcement, run migrations, check FK integrity, re-enable FKs.

    WHY:
      SQLite batch mode rebuilds tables as new CREATE TABLE statements.  While
      the rebuild is in progress the FK relationships are temporarily broken,
      which causes PRAGMA foreign_keys=ON to raise an error.  We therefore
      follow the documented SQLite migration pattern:
        1. PRAGMA foreign_keys=OFF   — suppress FK checks during rebuild
        2. Run all migrations inside a transaction
        3. PRAGMA foreign_key_check  — verify all FK relationships are still
                                        satisfied (raises if any row violates)
        4. PRAGMA foreign_keys=ON    — restore enforcement for normal operation
    """
    raw = getattr(connection, "connection", connection)  # unwrap SA connection → DBAPI
    raw.execute("PRAGMA foreign_keys=OFF")
    try:
        with context.begin_transaction():
            context.run_migrations()
        # Verify integrity after migration
        violations = raw.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                f"Foreign key violations detected after migration: {violations}"
            )
    finally:
        raw.execute("PRAGMA foreign_keys=ON")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and enables SQLite batch mode.
    Note: FK pragma management is not available in offline mode (no connection).
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
    Enables SQLite batch mode and the FK-safe migration pattern.
    """
    connection_override = config.attributes.get("connection", None)
    if connection_override is not None:
        _configure_context(connection_override)
        _disable_fk_and_run(connection_override)
        return

    url = get_url()
    connectable = create_db_engine(url)

    with connectable.connect() as connection:
        _configure_context(connection)
        _disable_fk_and_run(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
