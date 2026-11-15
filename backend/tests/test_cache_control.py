"""Tests for CacheControlMiddleware (T2.4-fixes Step 6).

Verifies that responses on paths starting with /auth or /projects (including 200, 401, 404,
and error responses) carry Cache-Control: no-store, while non-sensitive paths such as
/health do not.
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from alembic import command
from app.config import BACKEND_DIR, Settings
from app.db.session import create_db_engine, create_session_factory, get_db
from app.main import create_app
from app.services.auth_service import reset_rate_limiter


@pytest.fixture(autouse=True)
def clear_rate_limiter() -> Generator[None, None, None]:
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture()
def db_and_client(tmp_path: Path) -> Generator[tuple[Session, TestClient], None, None]:
    db_file = tmp_path / "test_cache_control.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    factory = create_session_factory(engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(
        Settings(
            cors_origins="http://localhost:3000",
            session_cookie_secure=False,
        )
    )
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app, raise_server_exceptions=True)

    db = factory()
    try:
        yield db, client
    finally:
        db.close()
        engine.dispose()


def test_cache_control_on_auth_me_authenticated(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /auth/me returns Cache-Control: no-store when authenticated."""
    _, client = db_and_client
    reg_resp = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert reg_resp.status_code == 201

    resp = client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_cache_control_on_projects_list(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects returns Cache-Control: no-store."""
    _, client = db_and_client
    client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "password123"},
    )

    resp = client.get("/projects")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_cache_control_on_error_responses(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Error responses on /auth and /projects carry Cache-Control: no-store."""
    _, client = db_and_client

    # 401 unauthenticated on /auth/me
    resp_unauth = client.get("/auth/me")
    assert resp_unauth.status_code == 401
    assert resp_unauth.headers.get("cache-control") == "no-store"

    # 404 not found on /projects/{id}
    client.post(
        "/auth/register",
        json={"email": "carol@example.com", "password": "password123"},
    )
    resp_404 = client.get("/projects/999999")
    assert resp_404.status_code == 404
    assert resp_404.headers.get("cache-control") == "no-store"

    # 401 bad password on /auth/login
    resp_bad_login = client.post(
        "/auth/login",
        json={"email": "carol@example.com", "password": "wrongpassword"},
    )
    assert resp_bad_login.status_code == 401
    assert resp_bad_login.headers.get("cache-control") == "no-store"


def test_health_does_not_have_no_store(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Non-sensitive endpoints such as /health do not get Cache-Control: no-store."""
    _, client = db_and_client
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") != "no-store"
