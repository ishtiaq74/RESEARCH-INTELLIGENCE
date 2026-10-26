"""Tests for T2.2 projects endpoints and repository.

Coverage:
  - Migration: projects table exists, columns correct, downgrade removes table,
    full lifecycle (upgrade → downgrade → upgrade), FK on owner_id enforced
  - Repository: create, list, get, update, delete all respect owner_id
  - Endpoints (unauthenticated):
      - All five routes return 401 without a session cookie
  - Endpoints (authenticated):
      - POST /projects: success 201, empty name 422, name too long 422
      - GET /projects: returns only caller's projects (empty list, multiple)
      - GET /projects/{id}: success 200, own project
      - PATCH /projects/{id}: success 200, updated name reflected
      - DELETE /projects/{id}: success 204, project gone after delete
  - Cross-user isolation (the most important set):
      - GET /projects lists ONLY the caller's projects (user B cannot see A's)
      - GET /projects/{id} returns 404 for another user's project
      - PATCH /projects/{id} returns 404 for another user's project
      - DELETE /projects/{id} returns 404 for another user's project

Each test uses a fresh in-memory (file) SQLite database with the full
migration applied, identical to the pattern in test_auth.py.
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.config import BACKEND_DIR, Settings
from app.db.session import create_db_engine, create_session_factory, get_db
from app.main import create_app
from app.repositories.project_repository import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
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
def db_and_client(tmp_path: Path) -> Generator[tuple[Session, TestClient], None, None]:
    """Yield (db_session, test_client) backed by a fresh migrated SQLite DB.

    Pattern mirrors test_auth.py so each test is fully isolated.
    session_cookie_secure=False so TestClient (HTTP) can read cookies.
    """
    db_file = tmp_path / "test_projects.db"
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


def _register_and_login(client: TestClient, email: str, password: str = "strongpass1") -> None:
    """Helper: register a user and leave the session cookie on the client."""
    resp = client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text


def _login(client: TestClient, email: str, password: str = "strongpass1") -> None:
    """Helper: log in an existing account and leave the session cookie on the client."""
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def migrated_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """Yield an engine connected to a fresh DB migrated to head."""
    db_file = tmp_path / "migration_projects_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    yield engine
    engine.dispose()


def test_projects_table_exists_after_upgrade(migrated_engine: Engine) -> None:
    """After upgrade head, the projects table must exist."""
    inspector = inspect(migrated_engine)
    tables = inspector.get_table_names()
    assert "projects" in tables, f"projects table not found; tables={tables}"


def test_projects_columns(migrated_engine: Engine) -> None:
    """projects table has all required columns."""
    inspector = inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns("projects")}
    assert columns >= {"id", "owner_id", "name", "created_at", "updated_at"}, (
        f"Missing columns in projects: {columns}"
    )


def test_projects_migration_downgrade_removes_table(tmp_path: Path) -> None:
    """Downgrade to projects migration's parent must remove the projects table."""
    db_file = tmp_path / "migration_down_projects.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    script = ScriptDirectory.from_config(alembic_cfg)
    projects_rev = next(
        s for s in script.walk_revisions() if "project" in (s.doc or "").lower()
    )
    parent_rev = str(projects_rev.down_revision)

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, parent_rev)  # downgrade projects migration

    engine = create_db_engine(db_url)
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "projects" not in tables, (
            f"projects table should be gone after downgrade; found {tables}"
        )
        assert "users" in tables, "users table should still exist after partial downgrade"
    finally:
        engine.dispose()


def test_projects_migration_full_lifecycle(tmp_path: Path) -> None:
    """Full cycle: upgrade head → downgrade to parent → upgrade head."""
    db_file = tmp_path / "migration_lifecycle_projects.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    script = ScriptDirectory.from_config(alembic_cfg)
    projects_rev = next(
        s for s in script.walk_revisions() if "project" in (s.doc or "").lower()
    )
    parent_rev = str(projects_rev.down_revision)
    head_rev = script.get_current_head()

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, parent_rev)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    try:
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == head_rev, f"Expected projects migration at head ({head_rev}), got {rev!r}"
    finally:
        engine.dispose()


def test_projects_owner_id_fk_enforced(tmp_path: Path) -> None:
    """owner_id FK is enforced: inserting a project with a non-existent user_id raises."""
    db_file = tmp_path / "migration_fk_projects.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    try:
        with engine.connect() as conn, pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO projects (owner_id, name, created_at, updated_at) "
                    "VALUES (9999, 'Ghost', '2026-01-01', '2026-01-01')"
                )
            )
            conn.commit()
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Repository-layer tests
# ---------------------------------------------------------------------------


def test_repo_create_project(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """create_project inserts a row and returns it with correct owner_id."""
    db, _ = db_and_client
    from app.repositories.user_repository import create_user
    from app.services.auth_service import hash_password

    user = create_user(db, "alice@example.com", hash_password("pw"))
    project = create_project(db, owner_id=user.id, name="My Project")

    assert project.id is not None
    assert project.owner_id == user.id
    assert project.name == "My Project"
    assert project.created_at is not None
    assert project.updated_at is not None


def test_repo_list_projects_filtered_by_owner(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """list_projects returns only the projects belonging to the specified owner_id."""
    db, _ = db_and_client
    from app.repositories.user_repository import create_user
    from app.services.auth_service import hash_password

    alice = create_user(db, "alice@example.com", hash_password("pw"))
    bob = create_user(db, "bob@example.com", hash_password("pw"))

    create_project(db, owner_id=alice.id, name="Alice Project 1")
    create_project(db, owner_id=alice.id, name="Alice Project 2")
    create_project(db, owner_id=bob.id, name="Bob Project")

    alice_projects = list_projects(db, owner_id=alice.id)
    bob_projects = list_projects(db, owner_id=bob.id)

    assert len(alice_projects) == 2
    assert all(p.owner_id == alice.id for p in alice_projects)
    assert len(bob_projects) == 1
    assert bob_projects[0].owner_id == bob.id


def test_repo_get_project_requires_owner_id(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """get_project(owner_id=A, project_id=B's project) returns None — not B's project."""
    db, _ = db_and_client
    from app.repositories.user_repository import create_user
    from app.services.auth_service import hash_password

    alice = create_user(db, "alice@example.com", hash_password("pw"))
    bob = create_user(db, "bob@example.com", hash_password("pw"))

    bob_project = create_project(db, owner_id=bob.id, name="Bob's Secret")

    # Alice cannot see Bob's project
    result = get_project(db, owner_id=alice.id, project_id=bob_project.id)
    assert result is None, "get_project must return None when owner_id does not match"


def test_repo_update_project_requires_owner_id(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """update_project(owner_id=A) cannot rename a project owned by B."""
    db, _ = db_and_client
    from app.repositories.user_repository import create_user
    from app.services.auth_service import hash_password

    alice = create_user(db, "alice@example.com", hash_password("pw"))
    bob = create_user(db, "bob@example.com", hash_password("pw"))

    bob_project = create_project(db, owner_id=bob.id, name="Bob's Project")

    result = update_project(db, owner_id=alice.id, project_id=bob_project.id, name="Hijacked")
    assert result is None, "update_project must return None when owner_id does not match"

    # Confirm Bob's project is unchanged
    unchanged = get_project(db, owner_id=bob.id, project_id=bob_project.id)
    assert unchanged is not None
    assert unchanged.name == "Bob's Project"


def test_repo_delete_project_requires_owner_id(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """delete_project(owner_id=A) cannot delete a project owned by B."""
    db, _ = db_and_client
    from app.repositories.user_repository import create_user
    from app.services.auth_service import hash_password

    alice = create_user(db, "alice@example.com", hash_password("pw"))
    bob = create_user(db, "bob@example.com", hash_password("pw"))

    bob_project = create_project(db, owner_id=bob.id, name="Bob's Project")

    deleted = delete_project(db, owner_id=alice.id, project_id=bob_project.id)
    assert deleted is False, "delete_project must return False when owner_id does not match"

    # Bob's project must still exist
    still_there = get_project(db, owner_id=bob.id, project_id=bob_project.id)
    assert still_there is not None


# ---------------------------------------------------------------------------
# Unauthenticated endpoint tests
# ---------------------------------------------------------------------------


def test_list_projects_requires_auth(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects without a session cookie returns 401."""
    _, client = db_and_client
    response = client.get("/projects")
    assert response.status_code == 401


def test_create_project_requires_auth(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """POST /projects without a session cookie returns 401."""
    _, client = db_and_client
    response = client.post("/projects", json={"name": "New"})
    assert response.status_code == 401


def test_get_project_requires_auth(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects/1 without a session cookie returns 401."""
    _, client = db_and_client
    response = client.get("/projects/1")
    assert response.status_code == 401


def test_patch_project_requires_auth(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """PATCH /projects/1 without a session cookie returns 401."""
    _, client = db_and_client
    response = client.patch("/projects/1", json={"name": "Renamed"})
    assert response.status_code == 401


def test_delete_project_requires_auth(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """DELETE /projects/1 without a session cookie returns 401."""
    _, client = db_and_client
    response = client.delete("/projects/1")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Authenticated endpoint tests — happy paths
# ---------------------------------------------------------------------------


def test_create_project_success(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """POST /projects returns 201 with the created project."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.post("/projects", json={"name": "My First Project"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "My First Project"
    assert "id" in body
    assert "owner_id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_create_project_empty_name_returns_422(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """POST /projects with an empty name returns 422."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.post("/projects", json={"name": ""})
    assert response.status_code == 422


def test_create_project_whitespace_only_name_returns_422(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """POST /projects with whitespace-only name returns 422."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.post("/projects", json={"name": "    \t  \n  "})
    assert response.status_code == 422


def test_create_project_name_strips_surrounding_whitespace(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """POST /projects strips leading/trailing whitespace before storing."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.post("/projects", json={"name": "   Trimmed Project   "})
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Trimmed Project"


def test_create_project_name_exactly_100_chars_accepted(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """POST /projects with a name of exactly 100 characters is accepted (201)."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    name_100 = "a" * 100
    response = client.post("/projects", json={"name": name_100})
    assert response.status_code == 201, response.text
    assert response.json()["name"] == name_100


def test_create_project_name_101_chars_rejected(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """POST /projects with a name of 101 characters returns 422."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    name_101 = "a" * 101
    response = client.post("/projects", json={"name": name_101})
    assert response.status_code == 422


def test_pydantic_schema_strips_before_length_check() -> None:
    """Verify Pydantic strips whitespace before validating min_length."""
    from pydantic import ValidationError

    from app.routers.projects import CreateProjectRequest, UpdateProjectRequest

    # Whitespace-only should fail min_length=1
    with pytest.raises(ValidationError):
        CreateProjectRequest(name="   ")

    with pytest.raises(ValidationError):
        UpdateProjectRequest(name="   ")

    # 100 chars with surrounding whitespace strips to 100 and passes
    req = CreateProjectRequest(name="  " + ("x" * 100) + "  ")
    assert len(req.name) == 100

    # 101 chars fails max_length=100
    with pytest.raises(ValidationError):
        CreateProjectRequest(name="x" * 101)


def test_project_service_name_validation() -> None:
    """Verify service-level _validate_project_name enforces stripping and length rules."""
    from app.services.project_service import ProjectError, _validate_project_name

    assert _validate_project_name("  valid name  ") == "valid name"
    assert len(_validate_project_name("x" * 100)) == 100

    with pytest.raises(ProjectError) as exc_empty:
        _validate_project_name("   ")
    assert exc_empty.value.status_code == 422

    with pytest.raises(ProjectError) as exc_long:
        _validate_project_name("x" * 101)
    assert exc_long.value.status_code == 422


def test_list_projects_empty(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects returns an empty list when the user has no projects."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.get("/projects")
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_list_projects_multiple(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects returns all of the caller's projects."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    client.post("/projects", json={"name": "Alpha"})
    client.post("/projects", json={"name": "Beta"})
    client.post("/projects", json={"name": "Gamma"})

    response = client.get("/projects")
    assert response.status_code == 200, response.text
    names = [p["name"] for p in response.json()]
    assert names == ["Alpha", "Beta", "Gamma"]


def test_list_projects_pagination_limit_and_offset(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects respects limit and offset, ordered by id ascending."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    for i in range(1, 6):
        client.post("/projects", json={"name": f"Project {i}"})

    # Page 1: limit 2, offset 0 -> Project 1, Project 2
    r1 = client.get("/projects?limit=2&offset=0")
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert len(data1) == 2
    assert [p["name"] for p in data1] == ["Project 1", "Project 2"]
    # Verify id ordering
    assert data1[0]["id"] < data1[1]["id"]

    # Page 2: limit 2, offset 2 -> Project 3, Project 4
    r2 = client.get("/projects?limit=2&offset=2")
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert len(data2) == 2
    assert [p["name"] for p in data2] == ["Project 3", "Project 4"]

    # Page 3: limit 2, offset 4 -> Project 5
    r3 = client.get("/projects?limit=2&offset=4")
    assert r3.status_code == 200, r3.text
    data3 = r3.json()
    assert len(data3) == 1
    assert [p["name"] for p in data3] == ["Project 5"]

    # Offset beyond available rows returns empty list
    r4 = client.get("/projects?limit=2&offset=10")
    assert r4.status_code == 200, r4.text
    assert r4.json() == []


def test_list_projects_limit_cap_100(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects with limit > 100 returns 422."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.get("/projects?limit=101")
    assert response.status_code == 422


def test_list_projects_negative_offset_returns_422(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects with negative offset returns 422."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.get("/projects?offset=-1")
    assert response.status_code == 422


def test_list_projects_limit_zero_returns_422(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects with limit=0 returns 422."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.get("/projects?limit=0")
    assert response.status_code == 422


def test_repository_list_projects_pagination(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """Verify project_repository.list_projects pagination parameters directly."""
    db, _ = db_and_client
    from app.repositories.user_repository import create_user
    from app.services.auth_service import hash_password

    user = create_user(db, "repo_page@example.com", hash_password("pass1234"))
    for i in range(1, 6):
        create_project(db, owner_id=user.id, name=f"Repo Project {i}")

    paged = list_projects(db, owner_id=user.id, limit=2, offset=1)
    assert len(paged) == 2
    assert paged[0].name == "Repo Project 2"
    assert paged[1].name == "Repo Project 3"


def test_get_project_success(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects/{id} returns the project when it belongs to the caller."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    created = client.post("/projects", json={"name": "My Project"}).json()
    response = client.get(f"/projects/{created['id']}")
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "My Project"


def test_get_project_not_found(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects/9999 returns 404 for a non-existent id."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.get("/projects/9999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_patch_project_not_found(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """PATCH /projects/9999 returns 404 for a non-existent id."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.patch("/projects/9999", json={"name": "Renamed"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_delete_project_not_found(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """DELETE /projects/9999 returns 404 for a non-existent id."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    response = client.delete("/projects/9999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_update_project_success(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """PATCH /projects/{id} renames the project and returns the updated resource."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    created = client.post("/projects", json={"name": "Old Name"}).json()
    response = client.patch(f"/projects/{created['id']}", json={"name": "New Name"})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "New Name"


def test_patch_project_whitespace_only_name_returns_422(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """PATCH /projects/{id} with whitespace-only name returns 422."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    created = client.post("/projects", json={"name": "Original Name"}).json()
    response = client.patch(f"/projects/{created['id']}", json={"name": "    \t  \n  "})
    assert response.status_code == 422


def test_patch_project_name_100_accepted_101_rejected(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """PATCH /projects/{id} accepts 100 chars and rejects 101 chars."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    created = client.post("/projects", json={"name": "Original"}).json()

    # 100 characters accepted
    r100 = client.patch(f"/projects/{created['id']}", json={"name": "x" * 100})
    assert r100.status_code == 200, r100.text
    assert r100.json()["name"] == "x" * 100

    # 101 characters rejected
    r101 = client.patch(f"/projects/{created['id']}", json={"name": "x" * 101})
    assert r101.status_code == 422


def test_delete_project_success(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """DELETE /projects/{id} returns 204 and the project is gone afterwards."""
    _, client = db_and_client
    _register_and_login(client, "alice@example.com")

    created = client.post("/projects", json={"name": "Temporary"}).json()
    delete_resp = client.delete(f"/projects/{created['id']}")
    assert delete_resp.status_code == 204

    get_resp = client.get(f"/projects/{created['id']}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-user isolation tests  (the critical security tests)
# ---------------------------------------------------------------------------


def test_list_projects_isolation(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects only returns the CALLER'S projects, never another user's.

    Alice creates two projects.  Bob creates one.  When Alice lists projects
    she sees only her two; when Bob lists he sees only his one.
    """
    db, client = db_and_client

    # Alice registers, creates projects, logs out
    _register_and_login(client, "alice@example.com")
    client.post("/projects", json={"name": "Alice-A"})
    client.post("/projects", json={"name": "Alice-B"})
    client.post("/auth/logout")

    # Bob registers, creates a project, then lists
    _register_and_login(client, "bob@example.com")
    client.post("/projects", json={"name": "Bob-C"})

    bob_list = client.get("/projects").json()
    assert len(bob_list) == 1
    assert bob_list[0]["name"] == "Bob-C"

    client.post("/auth/logout")

    # Alice logs back in and lists
    _login(client, "alice@example.com")
    alice_list = client.get("/projects").json()
    assert len(alice_list) == 2
    alice_names = {p["name"] for p in alice_list}
    assert alice_names == {"Alice-A", "Alice-B"}


def test_get_other_users_project_returns_404(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """GET /projects/{id} for a project owned by another user returns 404.

    The response body is identical to requesting a non-existent project id.
    """
    db, client = db_and_client

    # Alice creates a project
    _register_and_login(client, "alice@example.com")
    alice_project = client.post("/projects", json={"name": "Alice Secret"}).json()
    client.post("/auth/logout")

    # Bob tries to access it
    _register_and_login(client, "bob@example.com")
    cross_resp = client.get(f"/projects/{alice_project['id']}")
    nonexistent_resp = client.get("/projects/999999")

    assert cross_resp.status_code == 404
    assert nonexistent_resp.status_code == 404
    assert cross_resp.json() == nonexistent_resp.json()
    assert cross_resp.json() == {"detail": "Project not found."}


def test_patch_other_users_project_returns_404(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """PATCH /projects/{id} for a project owned by another user returns 404.

    The response body is identical to requesting a non-existent project id.
    """
    db, client = db_and_client

    _register_and_login(client, "alice@example.com")
    alice_project = client.post("/projects", json={"name": "Alice Project"}).json()
    client.post("/auth/logout")

    _register_and_login(client, "bob@example.com")
    cross_resp = client.patch(
        f"/projects/{alice_project['id']}", json={"name": "Bob Hijacked"}
    )
    nonexistent_resp = client.patch(
        "/projects/999999", json={"name": "Bob Hijacked"}
    )

    assert cross_resp.status_code == 404
    assert nonexistent_resp.status_code == 404
    assert cross_resp.json() == nonexistent_resp.json()
    assert cross_resp.json() == {"detail": "Project not found."}

    # Confirm Alice's project is unchanged
    client.post("/auth/logout")
    _login(client, "alice@example.com")
    unchanged = client.get(f"/projects/{alice_project['id']}").json()
    assert unchanged["name"] == "Alice Project"


def test_delete_other_users_project_returns_404(
    db_and_client: tuple[Session, TestClient],
) -> None:
    """DELETE /projects/{id} for a project owned by another user returns 404.

    The response body is identical to requesting a non-existent project id.
    """
    db, client = db_and_client

    _register_and_login(client, "alice@example.com")
    alice_project = client.post("/projects", json={"name": "Alice Project"}).json()
    client.post("/auth/logout")

    _register_and_login(client, "bob@example.com")
    cross_resp = client.delete(f"/projects/{alice_project['id']}")
    nonexistent_resp = client.delete("/projects/999999")

    assert cross_resp.status_code == 404
    assert nonexistent_resp.status_code == 404
    assert cross_resp.json() == nonexistent_resp.json()
    assert cross_resp.json() == {"detail": "Project not found."}

    # Confirm Alice's project still exists
    client.post("/auth/logout")
    _login(client, "alice@example.com")
    still_there = client.get(f"/projects/{alice_project['id']}")
    assert still_there.status_code == 200
