"""add projects table

Revision ID: e89a308107ea
Revises: 9f02bdd2f87e
Create Date: 2026-10-27 00:57:28.336492

WHY THIS MIGRATION:
  Introduces the projects table needed for T2.2 backend.

  projects:
    - id         surrogate PK
    - owner_id   FK → users.id (NOT NULL, CASCADE DELETE, indexed)
                 Index lets the database find all projects for a user quickly
                 without a full-table scan.
    - name       human-readable project title (max 200 chars, NOT NULL)
    - created_at UTC audit timestamp, set at insert
    - updated_at UTC audit timestamp, updated on every write

FK SAFETY (D-014):
  env.py disables PRAGMA foreign_keys before running migrations and runs
  PRAGMA foreign_key_check afterwards.  Creating a new table does not
  exercise the batch-mode FK risk, but the pattern is in place for future
  ALTER TABLE migrations.

OWNERSHIP NOTE:
  Every row has a non-nullable owner_id.  No project can exist without an
  owner — this is enforced at the database level, not only in application
  code.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e89a308107ea"
down_revision: str | Sequence[str] | None = "9f02bdd2f87e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the projects table with owner_id FK and index."""
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_projects_owner_id"), ["owner_id"], unique=False)


def downgrade() -> None:
    """Drop the projects table and its index."""
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_projects_owner_id"))

    op.drop_table("projects")
