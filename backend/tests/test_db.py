"""Tests for database engine, session, and configuration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, Settings, ensure_data_dir
from app.db.session import (
    create_db_engine,
    create_session_factory,
    get_db,
)


def test_connect_and_run_select_1(tmp_path: Path) -> None:
    """Engine successfully connects to a SQLite database and executes SELECT 1."""
    db_file = tmp_path / "test_select.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_db_engine(db_url)

    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1")).scalar()
        assert res == 1

    engine.dispose()


def test_pragma_foreign_keys_returns_1(tmp_path: Path) -> None:
    """PRAGMA foreign_keys returns 1 on every new connection."""
    db_file = tmp_path / "test_fk.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_db_engine(db_url)

    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert res == 1

    engine.dispose()


def test_pragma_journal_mode_returns_wal(tmp_path: Path) -> None:
    """PRAGMA journal_mode returns 'wal' on every new connection."""
    db_file = tmp_path / "test_wal.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_db_engine(db_url)

    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA journal_mode")).scalar()
        assert str(res).lower() == "wal"

    engine.dispose()


def test_settings_default_database_path_independent_of_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Settings default database path is identical regardless of current working directory."""
    dir_a = tmp_path / "cwd_folder_a"
    dir_b = tmp_path / "cwd_folder_b"
    dir_a.mkdir()
    dir_b.mkdir()

    # Ensure no environment variable overrides the default
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.chdir(dir_a)
    s1 = Settings()
    path1 = Path(s1.database_url.removeprefix("sqlite:///")).resolve()

    monkeypatch.chdir(dir_b)
    s2 = Settings()
    path2 = Path(s2.database_url.removeprefix("sqlite:///")).resolve()

    assert path1 == path2
    assert path1 == (BACKEND_DIR / "data" / "app.db").resolve()


def test_env_file_location_independent_of_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The .env file path in model_config is anchored to BACKEND_DIR."""
    dir_a = tmp_path / "cwd_folder_a"
    dir_b = tmp_path / "cwd_folder_b"
    dir_a.mkdir()
    dir_b.mkdir()

    monkeypatch.chdir(dir_a)
    s1 = Settings()
    env_path_1 = Path(str(s1.model_config.get("env_file"))).resolve()

    monkeypatch.chdir(dir_b)
    s2 = Settings()
    env_path_2 = Path(str(s2.model_config.get("env_file"))).resolve()

    assert env_path_1 == env_path_2
    assert env_path_1 == (BACKEND_DIR / ".env").resolve()


def test_database_url_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """DATABASE_URL environment variable overrides the default SQLite URL."""
    override_file = tmp_path / "custom_override.db"
    override_url = f"sqlite:///{override_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", override_url)

    s = Settings()
    assert s.database_url == override_url


def test_data_folder_created_automatically_when_missing(tmp_path: Path) -> None:
    """The directory containing the database is automatically created if missing."""
    missing_dir = tmp_path / "nested_missing_data_dir"
    missing_db = missing_dir / "app.db"
    assert not missing_dir.exists()

    db_url = f"sqlite:///{missing_db.as_posix()}"
    engine = create_db_engine(db_url)
    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1")).scalar()
        assert res == 1
    engine.dispose()

    assert missing_dir.exists()
    assert missing_dir.is_dir()
    assert missing_db.exists()

    # Also verify ensure_data_dir helper creates target dir if missing
    helper_target = tmp_path / "helper_created_dir"
    assert not helper_target.exists()
    created = ensure_data_dir(helper_target)
    assert created.exists()
    assert created.is_dir()


def test_get_db_session_dependency(tmp_path: Path) -> None:
    """get_db yields an active Session and closes it afterwards."""
    db_file = tmp_path / "test_session_dep.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    test_engine = create_db_engine(db_url)
    factory = create_session_factory(test_engine)

    with patch("app.db.session.SessionLocal", factory):
        gen = get_db()
        session = next(gen)
        assert isinstance(session, Session)
        assert session.is_active
        res = session.execute(text("SELECT 1")).scalar()
        assert res == 1

        with pytest.raises(StopIteration):
            next(gen)

    test_engine.dispose()
