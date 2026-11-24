"""SQLAlchemy ORM model for documents.

WHY A SEPARATE FILE:
  Keeping the Document model in its own module mirrors project.py and user.py,
  declaring one domain object per file.

WHY sqlite_autoincrement=True:
  In SQLite, AUTOINCREMENT guarantees rowids are monotonically increasing and
  never reused after deletion. This prevents deleted document IDs from ever being
  reassigned to a new upload, ensuring strong auditability and preventing stale
  references.

WHY project_id IS NOT NULLABLE WITH CASCADE DELETE:
  Every document belongs strictly to a project. When a project is deleted,
  all its documents are cascade-deleted at the database level.
"""
from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base

STATUS_UPLOADED: str = "uploaded"
STATUS_PROCESSING: str = "processing"
STATUS_READY: str = "ready"
STATUS_FAILED: str = "failed"
DOCUMENT_STATUSES: tuple[str, ...] = (
    STATUS_UPLOADED,
    STATUS_PROCESSING,
    STATUS_READY,
    STATUS_FAILED,
)


class Document(Base):
    """An uploaded research document (PDF) belonging to a single project.

    Columns
    -------
    id                : integer primary key (AUTOINCREMENT, never reused)
    project_id        : FK → projects.id (NOT NULL, indexed, CASCADE DELETE)
    original_filename : original uploaded filename from client (max 255 chars)
    stored_filename   : unique on-disk filename (e.g. <uuid>.pdf, max 64 chars, unique)
    sha256            : SHA-256 hex digest of file contents (64 chars)
    size_bytes        : file size in bytes
    page_count        : number of pages in the PDF (nullable, populated on probe)
    status            : processing status ('uploaded', 'processing', 'ready', 'failed')
    created_at        : UTC timestamp, set once at insert

    Constraints
    -----------
    UniqueConstraint(project_id, sha256)
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("project_id", "sha256", name="uq_documents_project_id_sha256"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_UPLOADED)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.datetime.now(datetime.UTC)
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} project_id={self.project_id} "
            f"stored_filename={self.stored_filename!r} status={self.status!r}>"
        )
