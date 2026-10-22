"""FTS5 full-text search availability and functionality check."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db.session import create_db_engine


def test_fts5_virtual_table_and_match(tmp_path: Path) -> None:
    """Create an FTS5 virtual table, insert a row, and find it with MATCH."""
    db_file = tmp_path / "test_fts5.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_db_engine(db_url)

    with engine.connect() as conn:
        conn.execute(
            text("CREATE VIRTUAL TABLE documents_fts USING fts5(title, body);")
        )
        conn.execute(
            text(
                "INSERT INTO documents_fts (title, body) "
                "VALUES (:title, :body);"
            ),
            {
                "title": "Attention Is All You Need",
                "body": (
                    "The dominant sequence transduction models "
                    "are based on complex neural networks."
                ),
            },
        )
        conn.commit()

        result = conn.execute(
            text(
                "SELECT title FROM documents_fts "
                "WHERE documents_fts MATCH :query;"
            ),
            {"query": "transduction"},
        ).fetchall()

        assert len(result) == 1
        assert result[0][0] == "Attention Is All You Need"

    engine.dispose()
