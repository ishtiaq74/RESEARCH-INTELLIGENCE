"""Document repository — database access layer for documents table.

WHY EVERY QUERY FILTERS BY owner_id AND project_id:
  Filtering by document_id alone would allow an authenticated caller to access
  or modify documents belonging to another user's project by guessing integer IDs.
  Joining Project with Project.owner_id == owner_id ensures the database structurally
  refuses to return or mutate any document row unless the calling user owns the project.

WHY create_document RE-CHECKS PROJECT OWNERSHIP:
  Even though the service checks project existence, verifying ownership inside
  create_document ensures that internal callers (background workers, bulk imports)
  cannot insert documents into projects owned by another user.
"""
from __future__ import annotations

import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import STATUS_UPLOADED, Document
from app.models.project import Project


class DuplicateDocumentError(Exception):
    """Raised when a document with the same sha256 already exists in the project."""


def create_document(
    db: Session,
    owner_id: int,
    project_id: int,
    original_filename: str,
    stored_filename: str,
    sha256: str,
    size_bytes: int,
    page_count: int | None = None,
    status: str = STATUS_UPLOADED,
) -> Document | None:
    """Insert a new document row into project_id if owned by owner_id.

    Returns the created Document, or None if the project does not exist or is not owned.
    Raises DuplicateDocumentError if a document with the same (project_id, sha256) exists.
    """
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == owner_id)
        .first()
    )
    if project is None:
        return None

    now = datetime.datetime.now(datetime.UTC)
    document = Document(
        project_id=project_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        sha256=sha256,
        size_bytes=size_bytes,
        page_count=page_count,
        status=status,
        created_at=now,
    )
    try:
        db.add(document)
        db.commit()
        db.refresh(document)
        return document
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateDocumentError(
            "A document with the same contents already exists in this project."
        ) from exc


def list_documents(
    db: Session,
    owner_id: int,
    project_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    """Return documents in project_id owned by owner_id, ordered by id ascending."""
    return (
        db.query(Document)
        .join(Project, Document.project_id == Project.id)
        .filter(
            Project.owner_id == owner_id,
            Document.project_id == project_id,
        )
        .order_by(Document.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_documents(
    db: Session,
    owner_id: int,
    project_id: int,
) -> int:
    """Return total count of documents in project_id owned by owner_id."""
    return (
        db.query(Document)
        .join(Project, Document.project_id == Project.id)
        .filter(
            Project.owner_id == owner_id,
            Document.project_id == project_id,
        )
        .count()
    )


def get_document(
    db: Session,
    owner_id: int,
    project_id: int,
    document_id: int,
) -> Document | None:
    """Return document by document_id in project_id owned by owner_id, or None."""
    return (
        db.query(Document)
        .join(Project, Document.project_id == Project.id)
        .filter(
            Project.owner_id == owner_id,
            Document.project_id == project_id,
            Document.id == document_id,
        )
        .first()
    )


def find_by_sha256(
    db: Session,
    owner_id: int,
    project_id: int,
    sha256: str,
) -> Document | None:
    """Return document by sha256 in project_id owned by owner_id, or None."""
    return (
        db.query(Document)
        .join(Project, Document.project_id == Project.id)
        .filter(
            Project.owner_id == owner_id,
            Document.project_id == project_id,
            Document.sha256 == sha256,
        )
        .first()
    )


def delete_document(
    db: Session,
    owner_id: int,
    project_id: int,
    document_id: int,
) -> bool:
    """Delete document by document_id in project_id if owned by owner_id.

    Returns True if deleted, False if not found or not owned.
    """
    doc = get_document(db, owner_id, project_id, document_id)
    if doc is None:
        return False
    db.delete(doc)
    db.commit()
    return True
