"""add documents table

Revision ID: b3a8c1f9d2e4
Revises: e89a308107ea
Create Date: 2026-11-25 01:45:00.000000

WHY THIS MIGRATION:
  Introduces the documents table for T3.1 upload and document management.

  documents:
    - id                surrogate PK with sqlite_autoincrement=True so IDs are never reused
    - project_id        FK → projects.id (NOT NULL, CASCADE DELETE, indexed)
    - original_filename original client filename (max 255 chars)
    - stored_filename   unique on-disk filename (max 64 chars, unique)
    - sha256            SHA-256 hex digest of file contents (64 chars)
    - size_bytes        file size in bytes
    - page_count        PDF page count (nullable)
    - status            processing status ('uploaded', 'processing', 'ready', 'failed')
    - created_at        UTC audit timestamp

CONSTRAINTS:
  - UniqueConstraint("stored_filename", name="uq_documents_stored_filename")
  - UniqueConstraint("project_id", "sha256", name="uq_documents_project_id_sha256")

FK SAFETY (D-014):
  env.py disables PRAGMA foreign_keys before running migrations and runs
  PRAGMA foreign_key_check afterwards. Creating a new table does not
  exercise the batch-mode FK risk, but the pattern is in place for future
  ALTER TABLE migrations.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3a8c1f9d2e4"
down_revision: str | Sequence[str] | None = "e89a308107ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create documents table with project_id FK, indexes, and constraints."""
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=64), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="uploaded"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename", name="uq_documents_stored_filename"),
        sa.UniqueConstraint("project_id", "sha256", name="uq_documents_project_id_sha256"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_documents_project_id"), ["project_id"], unique=False)


def downgrade() -> None:
    """Drop documents table and its index."""
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_project_id"))

    op.drop_table("documents")
