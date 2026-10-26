"""Tests for the T2 auth Alembic migration (users and sessions tables).

Verifies:
  - upgrade creates users and sessions tables with correct columns
  - downgrade removes both tables cleanly
  - full lifecycle (upgrade → downgrade → upgrade) works without error
  - FK constraint on sessions.user_id is enforced after migration
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.config import BACKEND_DIR
from app.db.session import create_db_engine


@pytest.fixture()
def migrated_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """Yield an engine connected to a fresh DB migrated to head."""
    db_file = tmp_path / "migration_auth_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    yield engine
    engine.dispose()


def test_users_table_exists_after_upgrade(migrated_engine: Engine) -> None:
    """After upgrade head, the users table must exist."""
    inspector = inspect(migrated_engine)
    tables = inspector.get_table_names()
    assert "users" in tables, f"users table not found; tables={tables}"


def test_sessions_table_exists_after_upgrade(migrated_engine: Engine) -> None:
    """After upgrade head, the sessions table must exist."""
    inspector = inspect(migrated_engine)
    tables = inspector.get_table_names()
    assert "sessions" in tables, f"sessions table not found; tables={tables}"


def test_users_columns(migrated_engine: Engine) -> None:
    """users table has the required columns."""
    inspector = inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns("users")}
    assert columns >= {"id", "email", "password_hash", "created_at"}, (
        f"Missing columns in users: {columns}"
    )


def test_sessions_columns(migrated_engine: Engine) -> None:
    """sessions table has the required columns."""
    inspector = inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns("sessions")}
    assert columns >= {"id", "user_id", "token_hash", "created_at", "expires_at"}, (
        f"Missing columns in sessions: {columns}"
    )


def test_auth_migration_downgrade_removes_tables(tmp_path: Path) -> None:
    """Downgrade to base must remove users and sessions."""
    db_file = tmp_path / "migration_down_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")

    engine = create_db_engine(db_url)
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "users" not in tables, f"users table should be gone after downgrade; found {tables}"
        assert "sessions" not in tables, (
            f"sessions table should be gone after downgrade; found {tables}"
        )
    finally:
        engine.dispose()


def test_auth_migration_full_lifecycle(tmp_path: Path) -> None:
    """Full cycle: upgrade → upgrade (idempotent) → downgrade → upgrade."""
    db_file = tmp_path / "migration_lifecycle_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    command.upgrade(alembic_cfg, "head")  # idempotent
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    try:
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            expected = "e89a308107ea"
            assert rev == expected, (
                f"Expected projects migration revision (head), got {rev!r}"
            )
    finally:
        engine.dispose()


def test_sessions_fk_enforced_after_migration(tmp_path: Path) -> None:
    """sessions.user_id FK is enforced: inserting with a missing user_id raises.

    This verifies that PRAGMA foreign_keys=ON is active after migration
    (the env.py restores it) and that the FK constraint was correctly
    created in the schema.
    """
    db_file = tmp_path / "migration_fk_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    try:
        with engine.connect() as conn, pytest.raises(IntegrityError):
            # Insert a session row with a non-existent user_id
            conn.execute(
                text(
                    "INSERT INTO sessions (user_id, token_hash, created_at, expires_at) "
                    "VALUES (9999, 'aabbcc', '2026-01-01', '2026-01-02')"
                )
            )
            conn.commit()
    finally:
        engine.dispose()
