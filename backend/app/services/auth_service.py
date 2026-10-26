"""Authentication service — business logic for register, login, logout, and session validation.

This layer sits between routers (HTTP concerns) and repositories (DB concerns).
Routers never touch DB sessions or model objects directly; they call service
functions which return simple domain objects.

WHY ARGON2ID:
  Argon2id won the 2015 Password Hashing Competition and is the OWASP-recommended
  algorithm as of 2023.  It is resistant to:
    - GPU brute force (memory-hard)
    - side-channel attacks (id variant combines the i and d variants)
  bcrypt is still safe but has a 72-byte password limit and is older.
  scrypt is memory-hard but has no standard parameter guidance.
  MD5 / SHA / plain storage are all unacceptable.

WHY GENERIC LOGIN ERROR:
  Returning "email not found" vs "wrong password" lets an attacker enumerate
  valid accounts (they learn who is registered).  A generic "invalid credentials"
  error reveals nothing.

WHY RATE LIMITING IN-PROCESS:
  A simple in-memory sliding-window limiter is proportionate for a local
  single-user app.  Redis/Celery would be over-engineering.  The limiter tracks
  failed attempts by email (lowercased) and blocks for a short backoff period.
  It resets on a successful login.  It is NOT distributed — if the server
  restarts the counter resets — but for this use case that is acceptable.
"""
from __future__ import annotations

import datetime
import secrets
import threading

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from sqlalchemy.orm import Session

from app import repositories
from app.models.user import User

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_ph = PasswordHasher()
# Argon2id with default parameters (time_cost=3, memory_cost=65536, parallelism=4).
# These are OWASP-recommended defaults for Argon2id.
_DUMMY_HASH: str = _ph.hash("dummy-password-not-a-real-credential")


def hash_password(plaintext: str) -> str:
    """Return an Argon2id hash of the plaintext password.

    NEVER log or store the plaintext argument.
    """
    return _ph.hash(plaintext)


def verify_password(password_hash: str, plaintext: str) -> bool:
    """Return True if plaintext matches the stored hash, False otherwise.

    Catches both VerifyMismatchError (valid hash, wrong password) and
    VerificationError (malformed/dummy hash).  Both return False so the
    caller never sees an exception from the hashing layer.
    """
    try:
        return _ph.verify(password_hash, plaintext)
    except (VerifyMismatchError, VerificationError):
        return False


# ---------------------------------------------------------------------------
# In-process login rate limiter
# ---------------------------------------------------------------------------

_SESSION_DURATION_HOURS: int = 24
_MAX_FAILED_ATTEMPTS: int = 10
_LOCKOUT_SECONDS: int = 60

# State: {lowercased_email: (failed_count, lockout_until)}
_rate_limit_state: dict[str, tuple[int, datetime.datetime | None]] = {}
_rate_limit_lock = threading.Lock()


def _is_locked_out(email: str) -> bool:
    """Return True if the email is currently under a lockout."""
    with _rate_limit_lock:
        state = _rate_limit_state.get(email)
        if state is None:
            return False
        count, until = state
        if count < _MAX_FAILED_ATTEMPTS:
            return False
        if until is None:
            return False
        return datetime.datetime.now(datetime.UTC) < until


def _record_failed(email: str) -> None:
    with _rate_limit_lock:
        state = _rate_limit_state.get(email, (0, None))
        count = state[0] + 1
        until: datetime.datetime | None = None
        if count >= _MAX_FAILED_ATTEMPTS:
            until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
                seconds=_LOCKOUT_SECONDS
            )
        _rate_limit_state[email] = (count, until)


def _record_success(email: str) -> None:
    with _rate_limit_lock:
        _rate_limit_state.pop(email, None)


def reset_rate_limiter() -> None:
    """Clear all rate-limit state.  Intended for use in tests only."""
    with _rate_limit_lock:
        _rate_limit_state.clear()


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

_MIN_PASSWORD_LENGTH: int = 8


def _validate_password(password: str) -> str | None:
    """Return an error message if password is too weak, or None if acceptable."""
    if len(password) < _MIN_PASSWORD_LENGTH:
        return f"Password must be at least {_MIN_PASSWORD_LENGTH} characters."
    return None


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Raised for authentication failures that should map to HTTP 4xx."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def register(db: Session, email: str, password: str) -> User:
    """Create and return a new user.

    Raises AuthError if the email is already registered or the password is weak.
    """
    email = email.lower().strip()

    # Check password rules before hitting the DB
    pw_error = _validate_password(password)
    if pw_error:
        raise AuthError(pw_error, status_code=422)

    if repositories.get_user_by_email(db, email) is not None:
        raise AuthError("Email already registered.", status_code=409)

    password_hash = hash_password(password)
    # NEVER log `password` here
    return repositories.create_user(db, email=email, password_hash=password_hash)


def login(db: Session, email: str, password: str) -> tuple[User, str]:
    """Verify credentials and create a server-side session.

    Returns (user, raw_token).  The raw token must be sent to the client as an
    httpOnly cookie; it is not stored in the DB (only its hash is).

    Raises AuthError with a GENERIC message on any credential failure.
    Rate-limits by email.
    """
    email = email.lower().strip()

    if _is_locked_out(email):
        raise AuthError(
            "Too many failed login attempts. Try again later.", status_code=429
        )

    user = repositories.get_user_by_email(db, email)
    # Always call verify_password even when no user was found.
    # WHY: if we returned early on missing user, the response time would be
    # shorter than for an existing user with a wrong password.  An attacker
    # could exploit that timing difference to enumerate valid emails.
    # We use module-level _DUMMY_HASH as the stand-in hash.
    # verify_password will return False (VerifyMismatchError) after running the
    # full Argon2id computation, giving the same wall-clock time as a real failed login.
    candidate_hash = user.password_hash if user is not None else _DUMMY_HASH
    ok = verify_password(candidate_hash, password)

    if user is None or not ok:
        _record_failed(email)
        raise AuthError("Invalid email or password.", status_code=401)

    _record_success(email)

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        hours=_SESSION_DURATION_HOURS
    )
    repositories.create_session(db, user_id=user.id, token=raw_token, expires_at=expires_at)
    return user, raw_token


def logout(db: Session, token: str) -> None:
    """Delete the session matching token.  No-op if token is unknown."""
    repositories.delete_session_by_token(db, token)


def get_current_user(db: Session, token: str | None) -> User | None:
    """Return the User for a valid, non-expired session token, or None.

    WHY CHECK expires_at IN APPLICATION CODE:
      We could add a WHERE clause in the repository, but checking here makes
      the expiry logic explicit and testable without a DB query.  We do filter
      in the repository query below for defence in depth.
    """
    if not token:
        return None

    session = repositories.get_session_by_token(db, token)
    if session is None:
        return None

    # Normalise: both timezone-aware comparison
    now = datetime.datetime.now(datetime.UTC)
    expires = session.expires_at
    # SQLite stores datetimes without timezone; treat as UTC
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=datetime.UTC)

    if now > expires:
        return None

    return repositories.get_user_by_id(db, session.user_id)
