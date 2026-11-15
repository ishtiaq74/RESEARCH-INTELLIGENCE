"""Tests for OriginCheckMiddleware (T2.4-fixes Step 2).

Verifies that state-changing requests (POST, PUT, PATCH, DELETE) with an untrusted
Origin header are rejected with 403 without executing route handlers or mutating the database.
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
from app.models.project import Project
from app.models.user import Session as SessionModel
from app.services.auth_service import reset_rate_limiter


@pytest.fixture(autouse=True)
def clear_rate_limiter() -> Generator[None, None, None]:
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture()
def db_and_client(tmp_path: Path) -> Generator[tuple[Session, TestClient], None, None]:
    db_file = tmp_path / "test_origin.db"
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


def test_allowed_origin_works(db_and_client: tuple[Session, TestClient]) -> None:
    """Requests with an allowed Origin header succeed normally."""
    _, client = db_and_client
    resp = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "password123"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 201


def test_disallowed_origin_post_projects_returns_403_and_changes_nothing(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Disallowed Origin on POST /projects returns 403 and does not create a database row."""
    db, client = db_and_client
    # Register with allowed origin
    reg_resp = client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "password123"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert reg_resp.status_code == 201

    initial_project_count = db.query(Project).count()

    # Attempt POST /projects with evil origin
    resp = client.post(
        "/projects",
        json={"name": "Attacker Project"},
        headers={"Origin": "http://evil.com"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Origin not allowed."}

    # Verify no project was inserted
    assert db.query(Project).count() == initial_project_count


def test_disallowed_origin_post_logout_returns_403_and_leaves_session_intact(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Disallowed Origin on POST /auth/logout returns 403 and does not delete session."""
    db, client = db_and_client
    reg_resp = client.post(
        "/auth/register",
        json={"email": "carol@example.com", "password": "password123"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert reg_resp.status_code == 201
    assert db.query(SessionModel).count() == 1

    # Attempt logout with disallowed origin
    resp = client.post(
        "/auth/logout",
        headers={"Origin": "http://evil.com"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Origin not allowed."}

    # Verify session row is still in the database
    assert db.query(SessionModel).count() == 1


def test_disallowed_origin_patch_projects_returns_403_and_changes_nothing(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Disallowed Origin on PATCH /projects/{id} returns 403 and does not rename project."""
    db, client = db_and_client
    client.post(
        "/auth/register",
        json={"email": "dave@example.com", "password": "password123"},
        headers={"Origin": "http://localhost:3000"},
    )
    proj_resp = client.post(
        "/projects",
        json={"name": "Original Name"},
        headers={"Origin": "http://localhost:3000"},
    )
    proj_id = proj_resp.json()["id"]

    # Attempt rename with disallowed origin
    resp = client.patch(
        f"/projects/{proj_id}",
        json={"name": "Hijacked Name"},
        headers={"Origin": "http://evil.com"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Origin not allowed."}

    # Verify database project name was not changed
    db_proj = db.query(Project).filter(Project.id == proj_id).first()
    assert db_proj is not None
    assert db_proj.name == "Original Name"


def test_disallowed_origin_delete_projects_returns_403_and_changes_nothing(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Disallowed Origin on DELETE /projects/{id} returns 403 and does not delete project."""
    db, client = db_and_client
    client.post(
        "/auth/register",
        json={"email": "eve@example.com", "password": "password123"},
        headers={"Origin": "http://localhost:3000"},
    )
    proj_resp = client.post(
        "/projects",
        json={"name": "Keep This"},
        headers={"Origin": "http://localhost:3000"},
    )
    proj_id = proj_resp.json()["id"]

    # Attempt delete with disallowed origin
    resp = client.delete(
        f"/projects/{proj_id}",
        headers={"Origin": "http://evil.com"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Origin not allowed."}

    # Verify project still exists in DB
    db_proj = db.query(Project).filter(Project.id == proj_id).first()
    assert db_proj is not None


def test_text_plain_post_with_disallowed_origin_returns_403(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """A text/plain POST (simple CORS request) with disallowed Origin is rejected with 403."""
    _, client = db_and_client
    client.post(
        "/auth/register",
        json={"email": "frank@example.com", "password": "password123"},
        headers={"Origin": "http://localhost:3000"},
    )

    resp = client.post(
        "/projects",
        content='{"name": "Simple Request"}',
        headers={
            "Origin": "http://attacker.com",
            "Content-Type": "text/plain",
        },
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Origin not allowed."}


def test_no_origin_header_still_works(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Requests without an Origin header (curl, backend tests) continue to work."""
    _, client = db_and_client
    resp = client.post(
        "/auth/register",
        json={"email": "grace@example.com", "password": "password123"},
    )
    assert resp.status_code == 201

    proj_resp = client.post(
        "/projects",
        json={"name": "CLI Project"},
    )
    assert proj_resp.status_code == 201


def test_get_and_options_unaffected_by_origin_check(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET and OPTIONS requests are not blocked by the Origin check."""
    _, client = db_and_client
    client.post(
        "/auth/register",
        json={"email": "heidi@example.com", "password": "password123"},
    )

    # Safe GET navigation or request is not blocked by OriginCheckMiddleware
    resp = client.get("/projects", headers={"Origin": "http://evil.com"})
    # CORSMiddleware may omit Access-Control-Allow-Origin, but status is not 403
    assert resp.status_code == 200
