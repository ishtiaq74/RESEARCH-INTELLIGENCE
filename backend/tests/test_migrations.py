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
    """Verify upgrade head, upgrade head again, downgrade base, and upgrade head lifecycle."""
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
