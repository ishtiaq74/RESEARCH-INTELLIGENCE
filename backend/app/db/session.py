"""Database engine and session management."""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _ensure_sqlite_parent_dir(url: str) -> None:
    """Ensure directory for SQLite database file exists before connecting."""
    if url.startswith("sqlite:///") and ":memory:" not in url:
        raw_path = url.removeprefix("sqlite:///")
        db_path = Path(raw_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str) -> Engine:
    """Create a synchronous SQLAlchemy engine configured for the given database URL.

    For SQLite:
    - Automatically creates parent directory if it does not exist.
    - Sets connect_args={"check_same_thread": False}.
    - Sets PRAGMA foreign_keys=ON and PRAGMA journal_mode=WAL on every new connection.
    """
    connect_args: dict[str, Any] = {}
    is_sqlite = database_url.startswith("sqlite")

    if is_sqlite:
        _ensure_sqlite_parent_dir(database_url)
        connect_args["check_same_thread"] = False

    engine = create_engine(database_url, connect_args=connect_args)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
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
