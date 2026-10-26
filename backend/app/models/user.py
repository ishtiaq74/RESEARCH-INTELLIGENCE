"""SQLAlchemy ORM models for authentication: users and sessions.

WHY SQLALCHEMY MODELS HERE:
  The models layer defines the database schema as Python classes.  Keeping them
  separate from the repositories layer means the schema is declared once; all
  query logic lives in repositories.  Any other layer (routers, services) never
  touches the database directly.

WHY users.email IS STORED LOWERCASE:
  Email addresses are case-insensitive per RFC 5321 (local part) and RFC 5322.
  Normalising to lowercase at storage time prevents duplicate accounts like
  User@example.com vs user@example.com and simplifies lookups.

WHY sessions.token_hash AND NOT sessions.token:
  The session token is a bearer credential.  If the sessions table is ever read
  (e.g. via SQL injection, backup leak, log scrape) the attacker learns valid
  tokens.  Storing only a SHA-256 hash means the token itself is never at rest;
  the attacker would also have to invert the hash.  The real token lives only in
  the httpOnly cookie on the client — it never touches application logs or DB
  columns.  This is the same reason password databases store hashes not
  plaintext passwords.
"""
from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.project import Project


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class User(Base):
    """Registered user account.

    Columns
    -------
    id           : surrogate primary key
    email        : unique, lowercased at write time (application responsibility)
    password_hash: Argon2id hash — never the plaintext password
    created_at   : UTC timestamp, set once at insert
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.datetime.now(datetime.UTC)
    )

    sessions: Mapped[list[Session]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(
        "Project", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


class Session(Base):
    """Server-side session record.

    WHY SERVER-SIDE SESSIONS:
      Client-side JWTs cannot be revoked before expiry — if a user logs out or
      a token is compromised, there is no way to invalidate it.  With server-side
      sessions the token is simply deleted from the DB on logout, which gives
      instant revocation.  This is appropriate for this application because the
      user base is small and the DB is local SQLite.

    Columns
    -------
    id         : surrogate primary key
    user_id    : FK → users.id (cascade delete)
    token_hash : SHA-256 hex digest of the random bearer token (see module docstring)
    created_at : UTC timestamp
    expires_at : UTC timestamp — the session is invalid after this point
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.datetime.now(datetime.UTC)
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<Session id={self.id} user_id={self.user_id} expires_at={self.expires_at!r}>"
