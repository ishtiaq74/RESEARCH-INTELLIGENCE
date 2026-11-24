"""Document service — business logic for uploaded documents.

This layer sits between routers (HTTP) and repositories/storage (DB and filesystem).
Routers never touch repositories or disk storage directly; they call service
functions which return model objects or raise domain exceptions.

WHY IDENTICAL 404 FOR MISSING AND NOT-OWNED PROJECTS:
  Returning 403 or a different error for a project owned by another user would reveal
  that the project exists. Raising ProjectNotFoundError("Project not found.") preserves
  strict isolation and prevents enumeration attacks.

WHY FILE DELETION ON INSERT FAILURE:
  If a document file is written to disk but database insertion fails (e.g. duplicate hash,
  constraint violation, connection drop), the stored file must be deleted immediately
  so orphan PDF files never accumulate on the filesystem.
"""
from __future__ import annotations

import logging
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.models.document import Document
from app.repositories import document_repository, project_repository
from app.repositories.document_repository import DuplicateDocumentError
from app.services.document_storage import (
    StorageError,
    StorageErrorCode,
    delete_stored_file,
    store_pdf,
)
from app.services.project_service import ProjectNotFoundError

logger = logging.getLogger("app.services.document_service")

_MAX_OFFSET: int = 1_000_000

_STORAGE_ERROR_STATUS_MAP: dict[StorageErrorCode, int] = {
    "too_large": 413,
    "not_pdf": 415,
    "corrupt": 422,
    "encrypted": 422,
    "empty": 422,
    "too_many_pages": 422,
}


class DocumentError(Exception):
    """Raised for document business logic failures that should map to HTTP 4xx."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class DocumentNotFoundError(DocumentError):
    """Raised when a document is not found or not owned by the caller."""

    def __init__(self, message: str = "Document not found.") -> None:
        super().__init__(message, status_code=404)


def _ensure_project_owned(db: Session, owner_id: int, project_id: int) -> None:
    """Verify that project_id exists and is owned by owner_id, raising ProjectNotFoundError."""
    project = project_repository.get_project(db, owner_id=owner_id, project_id=project_id)
    if project is None:
        raise ProjectNotFoundError("Project not found.")


def create_document(
    db: Session,
    owner_id: int,
    project_id: int,
    stream: BinaryIO,
    filename: str | None,
    cfg: Settings | None = None,
) -> Document:
    """Store an uploaded PDF file and create its database record.

    Validates:
      1. Project exists and belongs to owner_id (raises ProjectNotFoundError).
      2. Project has not reached max_documents_per_project limit (raises 422).
      3. File is a valid PDF within size and page limits (maps StorageError to 413/415/422).
      4. Duplicate file content (SHA-256) does not already exist in project (raises 409).

    If any failure occurs after the file has been stored on disk, the file is cleaned up.
    """
    _ensure_project_owned(db, owner_id=owner_id, project_id=project_id)

    app_cfg = cfg or settings
    current_count = document_repository.count_documents(
        db, owner_id=owner_id, project_id=project_id
    )
    if current_count >= app_cfg.max_documents_per_project:
        raise DocumentError(
            f"Project has reached the limit of {app_cfg.max_documents_per_project} documents.",
            status_code=422,
        )

    try:
        stored = store_pdf(
            stream,
            upload_dir=app_cfg.upload_dir,
            project_id=project_id,
            filename=filename,
            max_bytes=app_cfg.max_upload_bytes,
            max_pages=app_cfg.max_pdf_pages,
            probe_timeout=app_cfg.pdf_probe_timeout_seconds,
        )
    except StorageError as exc:
        status_code = _STORAGE_ERROR_STATUS_MAP.get(exc.code, 422)
        raise DocumentError(str(exc), status_code=status_code) from exc

    try:
        existing = document_repository.find_by_sha256(
            db, owner_id=owner_id, project_id=project_id, sha256=stored.sha256
        )
        if existing is not None:
            delete_stored_file(app_cfg.upload_dir, project_id, stored.stored_filename)
            raise DocumentError(
                "A document with the same contents already exists in this project.",
                status_code=409,
            )

        doc = document_repository.create_document(
            db,
            owner_id=owner_id,
            project_id=project_id,
            original_filename=stored.display_name,
            stored_filename=stored.stored_filename,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            page_count=stored.page_count,
        )
        if doc is None:
            delete_stored_file(app_cfg.upload_dir, project_id, stored.stored_filename)
            raise ProjectNotFoundError("Project not found.")
        return doc
    except DuplicateDocumentError as exc:
        delete_stored_file(app_cfg.upload_dir, project_id, stored.stored_filename)
        raise DocumentError(
            "A document with the same contents already exists in this project.",
            status_code=409,
        ) from exc
    except Exception:
        delete_stored_file(app_cfg.upload_dir, project_id, stored.stored_filename)
        raise


def list_documents(
    db: Session,
    owner_id: int,
    project_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    """Return documents belonging to project_id owned by owner_id with pagination."""
    if limit < 1 or limit > 100:
        raise DocumentError("Limit must be between 1 and 100.", status_code=422)
    if offset < 0 or offset > _MAX_OFFSET:
        raise DocumentError(
            f"Offset must be between 0 and {_MAX_OFFSET}.", status_code=422
        )
    _ensure_project_owned(db, owner_id=owner_id, project_id=project_id)
    return document_repository.list_documents(
        db, owner_id=owner_id, project_id=project_id, limit=limit, offset=offset
    )


def get_document(
    db: Session,
    owner_id: int,
    project_id: int,
    document_id: int,
) -> Document:
    """Return document by id in project_id owned by owner_id.

    Raises ProjectNotFoundError if the project is not owned / not found.
    Raises DocumentNotFoundError if the document is not found.
    """
    _ensure_project_owned(db, owner_id=owner_id, project_id=project_id)
    doc = document_repository.get_document(
        db, owner_id=owner_id, project_id=project_id, document_id=document_id
    )
    if doc is None:
        raise DocumentNotFoundError("Document not found.")
    return doc


def delete_document(
    db: Session,
    owner_id: int,
    project_id: int,
    document_id: int,
    cfg: Settings | None = None,
) -> None:
    """Delete document by id in project_id owned by owner_id, then remove its file.

    Raises ProjectNotFoundError if the project is not owned / not found.
    Raises DocumentNotFoundError if the document is not found.
    """
    _ensure_project_owned(db, owner_id=owner_id, project_id=project_id)
    doc = document_repository.get_document(
        db, owner_id=owner_id, project_id=project_id, document_id=document_id
    )
    if doc is None:
        raise DocumentNotFoundError("Document not found.")

    stored_filename = doc.stored_filename
    deleted = document_repository.delete_document(
        db, owner_id=owner_id, project_id=project_id, document_id=document_id
    )
    if not deleted:
        raise DocumentNotFoundError("Document not found.")

    app_cfg = cfg or settings
    try:
        delete_stored_file(app_cfg.upload_dir, project_id, stored_filename)
    except Exception as exc:
        logger.warning(
            "Failed to delete stored file %s for project %d: %s",
            stored_filename,
            project_id,
            exc,
        )
