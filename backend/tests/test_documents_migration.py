"""Tests for T3.1a-1 documents table migration and schema constraints."""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.config import BACKEND_DIR
from app.db.session import create_db_engine

DOC_COLUMNS = (
    "project_id, original_filename, stored_filename, "
    "sha256, size_bytes, page_count, status, created_at"
)


def _insert_doc(
    conn: Any,
    project_id: int,
    original_filename: str,
    stored_filename: str,
    sha256: str,
    size_bytes: int = 1000,
    page_count: int | None = 5,
    status: str = "uploaded",
    created_at: str = "2026-01-01 00:00:00",
) -> None:
    conn.execute(
        text(
            f"INSERT INTO documents ({DOC_COLUMNS}) "
            "VALUES (:project_id, :original_filename, :stored_filename, "
            ":sha256, :size_bytes, :page_count, :status, :created_at)"
        ),
        {
            "project_id": project_id,
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "page_count": page_count,
            "status": status,
            "created_at": created_at,
        },
    )


@pytest.fixture()
def migrated_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """Yield an engine connected to a fresh DB migrated to head."""
    db_file = tmp_path / "test_migration_docs.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    yield engine
    engine.dispose()


def test_documents_table_and_columns_exist_after_upgrade(migrated_engine: Engine) -> None:
    """After upgrade head, documents table exists with all required columns."""
    inspector = inspect(migrated_engine)
    tables = inspector.get_table_names()
    assert "documents" in tables, f"documents table not found in tables: {tables}"

    columns = {c["name"] for c in inspector.get_columns("documents")}
    expected_columns = {
        "id",
        "project_id",
        "original_filename",
        "stored_filename",
        "sha256",
        "size_bytes",
        "page_count",
        "status",
        "created_at",
    }
    assert columns >= expected_columns, (
        f"Missing columns in documents: {expected_columns - columns}"
    )


def test_documents_migration_downgrade_removes_table(tmp_path: Path) -> None:
    """Downgrade to documents parent revision removes the documents table."""
    db_file = tmp_path / "test_down_docs.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    script = ScriptDirectory.from_config(alembic_cfg)
    docs_rev = next(
        s for s in script.walk_revisions() if "document" in (s.doc or "").lower()
    )
    parent_rev = str(docs_rev.down_revision)

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, parent_rev)

    engine = create_db_engine(db_url)
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "documents" not in tables, (
            f"documents table should be removed after downgrade; found {tables}"
        )
        assert "projects" in tables, "projects table should remain after partial downgrade"
    finally:
        engine.dispose()


def test_documents_migration_full_lifecycle(tmp_path: Path) -> None:
    """Full lifecycle: upgrade head -> downgrade to parent -> upgrade head."""
    db_file = tmp_path / "test_lifecycle_docs.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    script = ScriptDirectory.from_config(alembic_cfg)
    docs_rev = next(
        s for s in script.walk_revisions() if "document" in (s.doc or "").lower()
    )
    parent_rev = str(docs_rev.down_revision)
    head_rev = script.get_current_head()

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, parent_rev)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    try:
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == head_rev, f"Expected head revision ({head_rev}), got {rev!r}"
    finally:
        engine.dispose()


def test_documents_project_id_fk_enforced(migrated_engine: Engine) -> None:
    """Inserting a document with a non-existent project_id raises IntegrityError."""
    with migrated_engine.connect() as conn, pytest.raises(IntegrityError):
        _insert_doc(
            conn,
            project_id=99999,
            original_filename="test.pdf",
            stored_filename="uuid1.pdf",
            sha256="hash1",
        )
        conn.commit()


def test_documents_unique_constraints(migrated_engine: Engine) -> None:
    """Unique constraints (project_id, sha256) and stored_filename are enforced."""
    with migrated_engine.connect() as conn:
        # Create user and two projects
        conn.execute(
            text(
                "INSERT INTO users (email, password_hash, created_at) "
                "VALUES ('user@example.com', 'hash', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO projects (owner_id, name, created_at, updated_at) "
                "VALUES (1, 'Project 1', '2026-01-01', '2026-01-01'), "
                "(1, 'Project 2', '2026-01-01', '2026-01-01')"
            )
        )
        # First document in project 1
        _insert_doc(
            conn,
            project_id=1,
            original_filename="paper.pdf",
            stored_filename="stored1.pdf",
            sha256="sha256_aaa",
        )
        conn.commit()

        # Duplicate (project_id, sha256) in same project should fail
        with pytest.raises(IntegrityError):
            _insert_doc(
                conn,
                project_id=1,
                original_filename="paper_copy.pdf",
                stored_filename="stored2.pdf",
                sha256="sha256_aaa",
            )
            conn.commit()
        conn.rollback()

        # Duplicate stored_filename should fail even across different projects
        with pytest.raises(IntegrityError):
            _insert_doc(
                conn,
                project_id=2,
                original_filename="other.pdf",
                stored_filename="stored1.pdf",
                sha256="sha256_bbb",
            )
            conn.commit()
        conn.rollback()

        # Same sha256 in a DIFFERENT project is allowed
        _insert_doc(
            conn,
            project_id=2,
            original_filename="paper_p2.pdf",
            stored_filename="stored3.pdf",
            sha256="sha256_aaa",
        )
        conn.commit()


def test_deleting_project_cascades_to_documents(migrated_engine: Engine) -> None:
    """Deleting a project removes its associated documents via ON DELETE CASCADE."""
    with migrated_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO users (email, password_hash, created_at) "
                "VALUES ('owner@example.com', 'hash', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO projects (owner_id, name, created_at, updated_at) "
                "VALUES (1, 'Cascade Test Project', '2026-01-01', '2026-01-01')"
            )
        )
        _insert_doc(
            conn,
            project_id=1,
            original_filename="doc.pdf",
            stored_filename="cascade_stored.pdf",
            sha256="sha256_cascade",
        )
        conn.commit()

        # Verify document exists
        count_query = text("SELECT count(*) FROM documents WHERE project_id = 1")
        count_before = conn.execute(count_query).scalar()
        assert count_before == 1

        # Delete project
        conn.execute(text("DELETE FROM projects WHERE id = 1"))
        conn.commit()

        # Verify document was cascaded
        count_after = conn.execute(count_query).scalar()
        assert count_after == 0
