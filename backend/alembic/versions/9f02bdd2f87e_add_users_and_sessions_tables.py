"""add users and sessions tables

Revision ID: 9f02bdd2f87e
Revises: 7c75c84bb53a
Create Date: 2026-10-26 01:24:14.483543

WHY THIS MIGRATION:
  Introduces the two tables needed for T2.1 backend authentication.

  users:
    - id             surrogate PK
    - email          unique, lowercased by application code, indexed for fast login lookup
    - password_hash  Argon2id hash (never plaintext)
    - created_at     audit timestamp

  sessions:
    - id             surrogate PK
    - user_id        FK → users.id, CASCADE DELETE so sessions are cleaned up with the user
    - token_hash     SHA-256 hex of the random bearer token; only the hash is stored at rest
    - created_at     audit timestamp
    - expires_at     the session is invalid after this UTC timestamp

FK SAFETY (D-014):
  env.py disables PRAGMA foreign_keys before running migrations and runs
  PRAGMA foreign_key_check afterwards.  New table creation does not
  exercise the batch-mode FK risk, but the pattern is in place for future
  ALTER TABLE migrations.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f02bdd2f87e"
down_revision: str | Sequence[str] | None = "7c75c84bb53a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create users and sessions tables."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sessions_token_hash"), ["token_hash"], unique=True)
        batch_op.create_index(batch_op.f("ix_sessions_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    """Drop sessions then users (order matters for FK constraint)."""
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_user_id"))
        batch_op.drop_index(batch_op.f("ix_sessions_token_hash"))

    op.drop_table("sessions")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_email"))

    op.drop_table("users")
