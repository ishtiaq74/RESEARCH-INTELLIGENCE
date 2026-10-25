"""Session repository — all DB access for the sessions table lives here.

WHY STORE ONLY THE TOKEN HASH:
  The session token is sent to the client as a cookie and acts like a password
  for that session.  If an attacker reads the sessions table (SQL injection,
  compromised backup, log scrape) they must not be able to replay a session.
  SHA-256(token) stored in the DB means:
    - the attacker would have to invert SHA-256 to obtain a valid token
    - the real token exists only in the client cookie and in transit (TLS)
  This is the same principle as storing password hashes instead of passwords.
"""
from __future__ import annotations

import datetime
import hashlib

from sqlalchemy.orm import Session as DBSession

from app.models.user import Session as SessionModel


def _hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a raw session token.

    WHY SHA-256 (not Argon2) for the token:
      Session tokens are long random strings (32+ bytes from secrets.token_urlsafe).
      Argon2 is designed to be slow to resist dictionary/brute-force attacks on
      low-entropy inputs like passwords.  A 256-bit random token has no such
      weakness — SHA-256 is adequate and fast for the lookup hot path.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: DBSession,
    user_id: int,
    token: str,
    expires_at: datetime.datetime,
) -> SessionModel:
    """Insert a session row and return it.

    Only token_hash is stored; the caller holds the raw token.
    """
    session = SessionModel(
        user_id=user_id,
        token_hash=_hash_token(token),
        created_at=datetime.datetime.now(datetime.UTC),
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session_by_token(db: DBSession, token: str) -> SessionModel | None:
    """Lookup a session by the raw token (hashes it internally)."""
    token_hash = _hash_token(token)
    return (
        db.query(SessionModel)
        .filter(SessionModel.token_hash == token_hash)
        .first()
    )


def delete_session_by_token(db: DBSession, token: str) -> int:
    """Delete the session matching token.  Returns number of rows deleted."""
    token_hash = _hash_token(token)
    deleted = (
        db.query(SessionModel)
        .filter(SessionModel.token_hash == token_hash)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def delete_expired_sessions(db: DBSession) -> int:
    """Remove all sessions whose expires_at is in the past.  Returns row count."""
    now = datetime.datetime.now(datetime.UTC)
    deleted = (
        db.query(SessionModel)
        .filter(SessionModel.expires_at < now)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
