"""Tests for app.services.document_service (business logic, storage, and isolation)."""
from __future__ import annotations

import io
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from alembic import command
from app.config import BACKEND_DIR, Settings
from app.db.session import create_db_engine, create_session_factory
from app.models.document import Document
from app.repositories.project_repository import create_project
from app.repositories.user_repository import create_user
from app.services.auth_service import hash_password
from app.services.document_service import (
    DocumentError,
    DocumentNotFoundError,
    create_document,
    delete_document,
    get_document,
    list_documents,
)
from app.services.document_storage import stored_file_path
from app.services.project_service import ProjectNotFoundError


def make_pdf_bytes(pages: int = 1, password: str | None = None) -> bytes:
    """Helper to generate valid, empty, or encrypted PDF bytes."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if password is not None:
        writer.encrypt(password, algorithm="RC4-128")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture()
def db_and_cfg(tmp_path: Path) -> Generator[tuple[Session, Settings], None, None]:
    """Yield a database session connected to a migrated SQLite DB and test Settings."""
    db_file = tmp_path / "test_docs_service.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    upload_dir = tmp_path / "uploads"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    factory = create_session_factory(engine)
    session = factory()

    cfg = Settings(
        cors_origins="http://localhost:3000",
        session_cookie_secure=False,
        upload_dir=upload_dir,
        max_upload_bytes=1_000_000,
        max_pdf_pages=10,
        max_documents_per_project=3,
        pdf_probe_timeout_seconds=5.0,
    )

    try:
        yield session, cfg
    finally:
        session.close()
        engine.dispose()


def test_create_document_success(db_and_cfg: tuple[Session, Settings]) -> None:
    """Valid PDF upload stores the file and creates a DB row."""
    db, cfg = db_and_cfg
    user = create_user(db, "alice@example.com", hash_password("pass"))
    project = create_project(db, user.id, "Alice Project")

    pdf_bytes = make_pdf_bytes(pages=2)
    doc = create_document(
        db,
        owner_id=user.id,
        project_id=project.id,
        stream=io.BytesIO(pdf_bytes),
        filename="test_paper.pdf",
        cfg=cfg,
    )

    assert doc.id is not None
    assert doc.project_id == project.id
    assert doc.original_filename == "test_paper.pdf"
    assert doc.page_count == 2
    assert doc.size_bytes == len(pdf_bytes)
    assert doc.status == "uploaded"

    path = stored_file_path(cfg.upload_dir, project.id, doc.stored_filename)
    assert path.is_file()
    assert path.read_bytes() == pdf_bytes


def test_create_document_limit_reached(db_and_cfg: tuple[Session, Settings]) -> None:
    """Exceeding max_documents_per_project raises DocumentError(422)."""
    db, cfg = db_and_cfg
    user = create_user(db, "alice@example.com", hash_password("pass"))
    project = create_project(db, user.id, "Alice Project")

    # max_documents_per_project is 3
    for i in range(3):
        create_document(
            db,
            user.id,
            project.id,
            io.BytesIO(make_pdf_bytes(pages=i + 1)),
            f"doc{i}.pdf",
            cfg=cfg,
        )

    with pytest.raises(DocumentError) as exc_info:
        create_document(
            db,
            user.id,
            project.id,
            io.BytesIO(make_pdf_bytes(pages=4)),
            "doc4.pdf",
            cfg=cfg,
        )
    assert exc_info.value.status_code == 422
    assert "limit of 3 documents" in str(exc_info.value)


def test_create_document_duplicate_in_same_project(
    db_and_cfg: tuple[Session, Settings],
) -> None:
    """Duplicate SHA-256 in the same project raises 409 and leaves no duplicate file."""
    db, cfg = db_and_cfg
    user = create_user(db, "alice@example.com", hash_password("pass"))
    project = create_project(db, user.id, "Alice Project")

    pdf_bytes = make_pdf_bytes(pages=1)
    doc1 = create_document(
        db, user.id, project.id, io.BytesIO(pdf_bytes), "first.pdf", cfg=cfg
    )

    with pytest.raises(DocumentError) as exc_info:
        create_document(
            db, user.id, project.id, io.BytesIO(pdf_bytes), "second.pdf", cfg=cfg
        )
    assert exc_info.value.status_code == 409
    assert "already exists in this project" in str(exc_info.value)

    # Check only one file exists on disk
    files = list(cfg.upload_dir.rglob("*.pdf"))
    assert len(files) == 1
    assert files[0].name == doc1.stored_filename


@pytest.mark.parametrize(
    ("payload", "expected_code", "error_match"),
    [
        (b"%PDF-" + b"x" * 2_000_000, 413, "too large"),
        (b"not a pdf at all", 415, "not a PDF"),
        (b"%PDF-1.7\n" + b"bad body" * 50, 422, "could not be read"),
        (make_pdf_bytes(pages=1, password="pw"), 422, "Encrypted"),
        (make_pdf_bytes(pages=0), 422, "no pages"),
        (make_pdf_bytes(pages=15), 422, "more than 10 pages"),
    ],
    ids=[
        "too_large",
        "not_pdf",
        "corrupt",
        "encrypted",
        "empty",
        "too_many_pages",
    ],
)
def test_storage_error_status_mappings(
    db_and_cfg: tuple[Session, Settings],
    payload: bytes,
    expected_code: int,
    error_match: str,
) -> None:
    """StorageError codes map to expected HTTP status codes and leave no files."""
    db, cfg = db_and_cfg
    user = create_user(db, "alice@example.com", hash_password("pass"))
    project = create_project(db, user.id, "Alice Project")

    with pytest.raises(DocumentError) as exc_info:
        create_document(
            db, user.id, project.id, io.BytesIO(payload), "file.pdf", cfg=cfg
        )
    assert exc_info.value.status_code == expected_code
    assert error_match in str(exc_info.value)
    # Ensure nothing stored
    stored_files = list(cfg.upload_dir.rglob("*.pdf"))
    assert stored_files == []


def test_insert_failure_deletes_stored_file(
    db_and_cfg: tuple[Session, Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If DB insert fails after file storage, stored file is deleted."""
    db, cfg = db_and_cfg
    user = create_user(db, "alice@example.com", hash_password("pass"))
    project = create_project(db, user.id, "Alice Project")

    from app.repositories import document_repository

    def mock_create_document(*args: Any, **kwargs: Any) -> Document | None:
        raise RuntimeError("Database connection crashed!")

    monkeypatch.setattr(document_repository, "create_document", mock_create_document)

    with pytest.raises(RuntimeError, match="Database connection crashed"):
        create_document(
            db,
            user.id,
            project.id,
            io.BytesIO(make_pdf_bytes()),
            "doc.pdf",
            cfg=cfg,
        )

    # Ensure file was cleaned up
    files = list(cfg.upload_dir.rglob("*.pdf"))
    assert files == []


def test_pagination_limits(db_and_cfg: tuple[Session, Settings]) -> None:
    """Pagination parameters are validated and sliced."""
    db, cfg = db_and_cfg
    user = create_user(db, "alice@example.com", hash_password("pass"))
    project = create_project(db, user.id, "Alice Project")

    for i in range(2):
        create_document(
            db,
            user.id,
            project.id,
            io.BytesIO(make_pdf_bytes(pages=i + 1)),
            f"doc{i}.pdf",
            cfg=cfg,
        )

    with pytest.raises(DocumentError) as e1:
        list_documents(db, user.id, project.id, limit=0)
    assert e1.value.status_code == 422

    with pytest.raises(DocumentError) as e2:
        list_documents(db, user.id, project.id, limit=101)
    assert e2.value.status_code == 422

    with pytest.raises(DocumentError) as e3:
        list_documents(db, user.id, project.id, offset=-1)
    assert e3.value.status_code == 422

    with pytest.raises(DocumentError) as e4:
        list_documents(db, user.id, project.id, offset=1_000_001)
    assert e4.value.status_code == 422

    # Valid pagination
    docs_p1 = list_documents(db, user.id, project.id, limit=1, offset=0)
    assert len(docs_p1) == 1
    docs_p2 = list_documents(db, user.id, project.id, limit=1, offset=1)
    assert len(docs_p2) == 1
    assert docs_p1[0].id != docs_p2[0].id


def test_delete_document_removes_row_and_file(
    db_and_cfg: tuple[Session, Settings],
) -> None:
    """Deleting a document removes the database row and the stored file on disk."""
    db, cfg = db_and_cfg
    user = create_user(db, "alice@example.com", hash_password("pass"))
    project = create_project(db, user.id, "Alice Project")

    doc = create_document(
        db,
        user.id,
        project.id,
        io.BytesIO(make_pdf_bytes()),
        "delete_me.pdf",
        cfg=cfg,
    )
    file_path = stored_file_path(cfg.upload_dir, project.id, doc.stored_filename)
    assert file_path.is_file()

    delete_document(db, user.id, project.id, doc.id, cfg=cfg)

    # Row is gone
    with pytest.raises(DocumentNotFoundError):
        get_document(db, user.id, project.id, doc.id)

    # File is gone
    assert not file_path.is_file()


def test_isolation_matrix(db_and_cfg: tuple[Session, Settings]) -> None:
    """ISOLATION MATRIX: User B cannot create, list, get, or delete in User A's project."""
    db, cfg = db_and_cfg
    user_a = create_user(db, "alice@example.com", hash_password("pass"))
    user_b = create_user(db, "bob@example.com", hash_password("pass"))

    proj_a = create_project(db, user_a.id, "Alice's Private Project")
    proj_b = create_project(db, user_b.id, "Bob's Project")

    pdf_a_bytes = make_pdf_bytes(pages=1)
    doc_a = create_document(
        db,
        user_a.id,
        proj_a.id,
        io.BytesIO(pdf_a_bytes),
        "alice_doc.pdf",
        cfg=cfg,
    )
    doc_b = create_document(
        db,
        user_b.id,
        proj_b.id,
        io.BytesIO(make_pdf_bytes(pages=2)),
        "bob_doc.pdf",
        cfg=cfg,
    )

    file_a = stored_file_path(cfg.upload_dir, proj_a.id, doc_a.stored_filename)
    assert file_a.is_file()

    # 1. Nonexistent project comparison baseline
    with pytest.raises(ProjectNotFoundError) as nonexistent_err:
        get_document(db, user_b.id, project_id=99999, document_id=1)
    expected_msg = str(nonexistent_err.value)
    assert expected_msg == "Project not found."

    # 2. B cannot create in A's project -> same ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError) as exc_create:
        create_document(
            db,
            user_b.id,
            proj_a.id,
            io.BytesIO(make_pdf_bytes()),
            "b_hack.pdf",
            cfg=cfg,
        )
    assert str(exc_create.value) == expected_msg

    # 3. B cannot list in A's project -> same ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError) as exc_list:
        list_documents(db, user_b.id, proj_a.id)
    assert str(exc_list.value) == expected_msg

    # 4. B cannot get A's document via A's project id -> same ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError) as exc_get:
        get_document(db, user_b.id, proj_a.id, doc_a.id)
    assert str(exc_get.value) == expected_msg

    # 5. B cannot get A's document even when passing B's project id -> DocumentNotFoundError
    with pytest.raises(DocumentNotFoundError):
        get_document(db, user_b.id, proj_b.id, doc_a.id)

    # 6. B cannot delete A's document -> same ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError) as exc_del:
        delete_document(db, user_b.id, proj_a.id, doc_a.id, cfg=cfg)
    assert str(exc_del.value) == expected_msg

    # 7. B's list never shows A's documents
    b_docs = list_documents(db, user_b.id, proj_b.id)
    assert len(b_docs) == 1
    assert b_docs[0].id == doc_b.id
    assert b_docs[0].id != doc_a.id

    # 8. A's document row and file remain completely unchanged after B's failed attempts
    fresh_doc_a = get_document(db, user_a.id, proj_a.id, doc_a.id)
    assert fresh_doc_a.id == doc_a.id
    assert fresh_doc_a.stored_filename == doc_a.stored_filename
    assert file_a.is_file()
    assert file_a.read_bytes() == pdf_a_bytes
