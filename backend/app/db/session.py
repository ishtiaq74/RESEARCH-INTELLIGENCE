"""Database engine and session management."""
from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _make_sqlite_parent_dir(url: str) -> None:
    """Create the parent directory of a SQLite database file if it does not exist.

    Must be called before the sqlite3 connection is opened because sqlite3 cannot
    create directories itself.  We call it from a custom creator so it runs lazily
    on first use, not at engine construction / module import time.
    """
    if url.startswith("sqlite:///") and ":memory:" not in url:
        raw_path = url.removeprefix("sqlite:///")
        db_path = Path(raw_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)


def _make_sqlite_creator(database_url: str) -> Any:
    """Return a DBAPI creator function that ensures the parent dir exists before connecting.

    Using a custom creator lets us run directory-creation lazily—only when
    the first real connection is requested—rather than at engine-construction time.
    """
    # Extract path from sqlite:///path
    raw_path = database_url.removeprefix("sqlite:///")

    def creator() -> sqlite3.Connection:
        _make_sqlite_parent_dir(database_url)
        return sqlite3.connect(raw_path, check_same_thread=False)

    return creator


def create_db_engine(database_url: str) -> Engine:
    """Create a synchronous SQLAlchemy engine configured for the given database URL.

    For SQLite:
    - Parent directory is created lazily on the FIRST CONNECTION (not at engine
      construction time), so importing this module has no filesystem side-effects.
    - Uses a custom creator function so check_same_thread=False is set correctly.
    - Sets PRAGMA foreign_keys=ON and PRAGMA journal_mode=WAL on every new connection.
    """
    is_sqlite = database_url.startswith("sqlite")

    if is_sqlite and ":memory:" not in database_url:
        engine = create_engine(
            database_url,
            creator=_make_sqlite_creator(database_url),
        )
    elif is_sqlite:
        # in-memory SQLite; no custom creator needed
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(database_url)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection: Any, connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = create_db_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_session_factory(custom_engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to a specific engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=custom_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
