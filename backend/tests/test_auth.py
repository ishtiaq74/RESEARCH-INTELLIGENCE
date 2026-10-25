"""Tests for the auth endpoints and service.

Coverage:
  - Registration: success, duplicate email, short password
  - Login: success, wrong password, non-existent email, generic error message
  - Logout: clears cookie and invalidates session
  - /auth/me: returns user when authenticated, 401 when not, 401 after logout
  - Expired session: GET /auth/me returns 401 after session expires
  - Password stored hashed (not plaintext)
  - Token stored hashed (not plaintext)
  - Protected route returns 401 without a cookie

Each test uses an isolated in-memory SQLite database and a migration-applied
schema, so tests are fully independent and do not touch the real data/app.db.
"""
from __future__ import annotations

import datetime
import hashlib
from collections.abc import Generator
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, Settings
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
from app.models.user import Session as SessionModel
from app.models.user import User
from app.services.auth_service import reset_rate_limiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_rate_limiter() -> Generator[None, None, None]:
    """Reset the in-process rate limiter before every test."""
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture()
def db_and_client(tmp_path: pytest.TempPathFactory) -> Generator[  # type: ignore[type-arg]
    tuple[Session, TestClient], None, None
]:
    """Yield (db_session, test_client) backed by a fresh in-memory DB.

    Uses a real SQLite file (not :memory:) so Alembic migrations work.
    Each test gets its own tmp_path so they are fully isolated.
    """
    db_file = tmp_path / "test_auth.db"  # type: ignore[operator]
    db_url = f"sqlite:///{db_file.as_posix()}"

    # Apply migrations to get the real schema
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    factory = create_session_factory(engine)

    # Override get_db to use our test engine
    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(Settings(cors_origins="http://localhost:3000"))
    app.dependency_overrides[__import__("app.db.session", fromlist=["get_db"]).get_db] = (
        override_get_db
    )

    client = TestClient(app, raise_server_exceptions=True)

    db = factory()
    try:
        yield db, client
    finally:
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_success(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Successful registration returns 201 and sets a session cookie."""
    db, client = db_and_client
    response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "strongpass1"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "id" in body
    # Session cookie must be set
    assert "session" in response.cookies, "Expected a session cookie after register"


def test_register_email_case_insensitive(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Emails are normalised to lowercase."""
    db, client = db_and_client
    response = client.post(
        "/auth/register",
        json={"email": "ALICE@EXAMPLE.COM", "password": "strongpass1"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "alice@example.com"


def test_register_duplicate_email_returns_409(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Registering the same email twice returns 409 Conflict."""
    db, client = db_and_client
    payload = {"email": "bob@example.com", "password": "strongpass1"}
    assert client.post("/auth/register", json=payload).status_code == 201
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 409


def test_register_short_password_returns_422(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """A password shorter than 8 characters returns 422 Unprocessable Entity."""
    db, client = db_and_client
    response = client.post(
        "/auth/register",
        json={"email": "carol@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_password_stored_hashed(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """The password_hash column must never contain the plaintext password.

    WHY: if the DB is compromised, attackers must crack Argon2id rather than
    reading plaintext passwords directly.
    """
    db, client = db_and_client
    plaintext = "strongpass1"
    client.post("/auth/register", json={"email": "dave@example.com", "password": plaintext})

    user = db.query(User).filter(User.email == "dave@example.com").first()
    assert user is not None
    assert plaintext not in user.password_hash, (
        "Plaintext password must not appear in the password_hash column"
    )
    assert user.password_hash.startswith("$argon2"), (
        f"Expected Argon2 hash format, got: {user.password_hash[:20]!r}"
    )


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


def test_login_success(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Correct credentials return 200 and set a session cookie."""
    db, client = db_and_client
    client.post("/auth/register", json={"email": "eve@example.com", "password": "password123"})
    # Clear cookies from register
    client.cookies.clear()

    response = client.post(
        "/auth/login",
        json={"email": "eve@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    assert "session" in response.cookies


def test_login_wrong_password_returns_401(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Wrong password returns 401."""
    db, client = db_and_client
    client.post("/auth/register", json={"email": "frank@example.com", "password": "password123"})
    client.cookies.clear()

    response = client.post(
        "/auth/login",
        json={"email": "frank@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_nonexistent_email_returns_401(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Non-existent email returns 401 (not 404 — do not reveal email existence)."""
    db, client = db_and_client
    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "password123"},
    )
    assert response.status_code == 401


def test_login_generic_error_message(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """The error message for bad credentials must not reveal whether the email exists.

    WHY: returning different messages for 'email not found' vs 'wrong password'
    allows an attacker to enumerate valid accounts by probing the API.
    """
    db, client = db_and_client
    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "password123"},
    )
    detail = response.json().get("detail", "")
    assert "email" in detail.lower() or "password" in detail.lower(), (
        "Error message should be generic about credentials"
    )
    # Must not reveal that the email doesn't exist
    assert "not found" not in detail.lower(), (
        f"Error message must not reveal missing email: {detail!r}"
    )
    assert "exist" not in detail.lower(), (
        f"Error message must not reveal missing email: {detail!r}"
    )


def test_token_stored_hashed(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """The sessions table must store only the SHA-256 hash of the token, not the token itself.

    WHY: if the sessions table is leaked, the attacker must invert SHA-256 to
    obtain a valid token.  The raw token only ever lives in the client cookie.
    """
    db, client = db_and_client
    client.post("/auth/register", json={"email": "grace@example.com", "password": "password123"})
    client.cookies.clear()

    response = client.post(
        "/auth/login", json={"email": "grace@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    raw_token = response.cookies.get("session")
    assert raw_token is not None

    session_row = db.query(SessionModel).first()
    assert session_row is not None

    # token_hash must NOT be the raw token
    assert session_row.token_hash != raw_token, (
        "Raw token must not be stored in the sessions table"
    )

    # token_hash MUST be the SHA-256 hex digest
    expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    assert session_row.token_hash == expected_hash, (
        "sessions.token_hash must be SHA-256(raw_token)"
    )


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


def test_logout_clears_cookie(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """POST /auth/logout clears the session cookie."""
    db, client = db_and_client
    client.post("/auth/register", json={"email": "henry@example.com", "password": "password123"})

    response = client.post("/auth/logout")
    assert response.status_code == 204
    # Cookie should be cleared (set to empty or expired)
    # TestClient may remove it from cookies after a delete_cookie response
    assert response.cookies.get("session", None) in (None, "")


def test_logout_invalidates_session(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """After logout, GET /auth/me returns 401."""
    db, client = db_and_client
    client.post("/auth/register", json={"email": "iris@example.com", "password": "password123"})

    # Verify we are authenticated
    me_response = client.get("/auth/me")
    assert me_response.status_code == 200

    # Logout
    client.post("/auth/logout")

    # Now /me should return 401
    me_after = client.get("/auth/me")
    assert me_after.status_code == 401


# ---------------------------------------------------------------------------
# /auth/me tests
# ---------------------------------------------------------------------------


def test_me_returns_user_when_authenticated(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /auth/me returns user info when a valid session cookie is present."""
    db, client = db_and_client
    client.post("/auth/register", json={"email": "jack@example.com", "password": "password123"})

    response = client.get("/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "jack@example.com"
    assert "password" not in body, "password must not appear in the /me response"
    assert "password_hash" not in body, "password_hash must not appear in the /me response"


def test_me_returns_401_without_cookie(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /auth/me returns 401 when no session cookie is present.

    This also covers the general 'protected route without a cookie' requirement.
    """
    db, client = db_and_client
    # No registration — no cookie
    response = client.get("/auth/me")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Expired session test
# ---------------------------------------------------------------------------


def test_expired_session_returns_401(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /auth/me returns 401 when the session has expired.

    We set the session's expires_at to the past directly in the DB to simulate
    expiry without sleeping.
    """
    db, client = db_and_client
    client.post("/auth/register", json={"email": "kate@example.com", "password": "password123"})

    # Confirm authenticated
    assert client.get("/auth/me").status_code == 200

    # Expire the session by setting expires_at in the past
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    db.query(SessionModel).update({"expires_at": past})
    db.commit()

    response = client.get("/auth/me")
    assert response.status_code == 401, "Expired session must return 401"
