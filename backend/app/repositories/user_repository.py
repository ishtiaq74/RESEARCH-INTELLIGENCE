"""User repository — all DB access for the users table lives here.

WHY A REPOSITORIES LAYER:
  Routers and services should not write SQL.  When they do, any change to the
  schema or query strategy requires hunting through business-logic code.
  The repository pattern centralises all data access in one place:
    - the schema can change (column rename, index tweak) without touching routers
    - queries are easy to find, read and test in isolation
    - in future, swapping SQLite for PostgreSQL only requires checking this file
  This is especially important for owner-scoping: every query that touches
  user-owned data must filter by owner_id.  Enforcing that rule is easier when
  all queries are in repositories.
"""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    """Return the User with the given (already lowercased) email, or None."""
    return db.query(User).filter(User.email == email.lower()).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Return the User with the given id, or None."""
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, email: str, password_hash: str) -> User:
    """Insert a new user row and return it.

    email is stored lowercased so lookups are case-insensitive.
    password_hash must already be an Argon2id digest — never pass plaintext here.
    created_at is set by the ORM default.
    """
    user = User(
        email=email.lower(),
        password_hash=password_hash,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
