"""Tests for Alembic database migrations."""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.config import BACKEND_DIR
from app.db.session import create_db_engine


def test_alembic_migration_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify upgrade head, upgrade head again, downgrade base, and upgrade head lifecycle.

    Uses explicit set_main_option to override the database URL in alembic config.
    This tests the connection_override path in env.py's run_migrations_online().
    """
    temp_db = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{temp_db.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)

    alembic_ini_path = BACKEND_DIR / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. upgrade head
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    with engine.connect() as conn:
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert rev is not None

    # 2. upgrade head again (idempotency check)
    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        rev_again = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert rev_again == rev

    # 3. downgrade base
    command.downgrade(alembic_cfg, "base")

    with engine.connect() as conn:
        base_rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        assert len(base_rows) == 0

    # 4. upgrade head
    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        rev_final = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert rev_final == rev

    engine.dispose()


def test_alembic_migration_via_settings_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify the Settings/DATABASE_URL path in env.py's get_url().

    This test does NOT call set_main_option('sqlalchemy.url', ...).
    The database is set ONLY via monkeypatch.setenv('DATABASE_URL', ...).
    This proves that env.py's get_url() falls through to Settings().database_url
    when sqlalchemy.url is absent from the config.

    Also proves the real backend/data/app.db was not created or modified.
    """
    temp_db = tmp_path / "settings_path_test.db"
    db_url = f"sqlite:///{temp_db.as_posix()}"

    # Record state of real data dir before test
    real_db = BACKEND_DIR / "data" / "app.db"
    real_db_existed_before = real_db.exists()
    real_db_mtime_before = real_db.stat().st_mtime if real_db_existed_before else None

    engine = None
    try:
        # Set DATABASE_URL env var — this is the ONLY place we set the DB target
        monkeypatch.setenv("DATABASE_URL", db_url)

        alembic_ini_path = BACKEND_DIR / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini_path))

        # Assert that sqlalchemy.url is NOT set in the config (the key test precondition)
        ini_url = alembic_cfg.get_main_option("sqlalchemy.url")
        assert ini_url is None, (
            f"Expected sqlalchemy.url to be absent from alembic.ini, but got: {ini_url!r}. "
            "The test must exercise the Settings() fallback path in get_url()."
        )

        # Run the full lifecycle: upgrade, upgrade again, downgrade, upgrade
        command.upgrade(alembic_cfg, "head")

        engine = create_db_engine(db_url)
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev is not None, "Expected a migration revision after upgrade head"

        command.upgrade(alembic_cfg, "head")

        with engine.connect() as conn:
            rev_again = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev_again == rev

        command.downgrade(alembic_cfg, "base")

        with engine.connect() as conn:
            base_rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            assert len(base_rows) == 0

        command.upgrade(alembic_cfg, "head")

        with engine.connect() as conn:
            rev_final = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev_final == rev
    finally:
        if engine is not None:
            engine.dispose()

        # Prove the real data/app.db was not created or modified during this test
        real_db_exists_after = real_db.exists()
        if not real_db_existed_before:
            assert not real_db_exists_after, (
                f"The real database at {real_db} was created during the test. "
                "The test must only touch the tmp_path database."
            )
        else:
            real_db_mtime_after = real_db.stat().st_mtime
            assert real_db_mtime_after == real_db_mtime_before, (
                f"The real database at {real_db} was modified during the test. "
                f"mtime before: {real_db_mtime_before}, after: {real_db_mtime_after}"
            )
