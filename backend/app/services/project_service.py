"""Project service — business logic for projects.

This layer sits between routers (HTTP concerns) and repositories (DB concerns).
Routers never touch repositories or database queries directly; they call service
functions which return model objects or raise domain exceptions.

WHY IDENTICAL 404 FOR MISSING AND NOT-OWNED PROJECTS:
  Returning 403 on a project owned by another user would reveal that the
  project exists. Returning 404 with the identical message ("Project not found.")
  prevents enumeration and ensures an attacker cannot discover whether an ID
  belongs to another user or does not exist at all.

WHY OWNERSHIP FLOWS INTO EVERY QUERY:
  Passing owner_id from the service to the repository ensures that ownership
  scoping is enforced in the data layer itself. No operation can bypass the
  user isolation boundary.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.project import Project
from app.repositories import project_repository


class ProjectError(Exception):
    """Raised for project business logic failures that should map to HTTP 4xx."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProjectNotFoundError(ProjectError):
    """Raised when a project is not found or not owned by the caller.

    Maps to HTTP 404 with identical message regardless of whether the row
    does not exist or belongs to a different owner.
    """

    def __init__(self, message: str = "Project not found.") -> None:
        super().__init__(message, status_code=404)


def create_project(db: Session, owner_id: int, name: str) -> Project:
    """Create a new project owned by owner_id."""
    return project_repository.create_project(db, owner_id=owner_id, name=name)


def list_projects(db: Session, owner_id: int) -> list[Project]:
    """Return all projects owned by owner_id."""
    return project_repository.list_projects(db, owner_id=owner_id)


def get_project(db: Session, owner_id: int, project_id: int) -> Project:
    """Return a single project owned by owner_id.

    Raises ProjectNotFoundError if the project does not exist or is not owned by owner_id.
    """
    project = project_repository.get_project(
        db, owner_id=owner_id, project_id=project_id
    )
    if project is None:
        raise ProjectNotFoundError("Project not found.")
    return project


def update_project(
    db: Session, owner_id: int, project_id: int, name: str
) -> Project:
    """Rename a project owned by owner_id.

    Raises ProjectNotFoundError if the project does not exist or is not owned by owner_id.
    """
    project = project_repository.update_project(
        db, owner_id=owner_id, project_id=project_id, name=name
    )
    if project is None:
        raise ProjectNotFoundError("Project not found.")
    return project


def delete_project(db: Session, owner_id: int, project_id: int) -> None:
    """Delete a project owned by owner_id.

    Raises ProjectNotFoundError if the project does not exist or is not owned by owner_id.
    """
    deleted = project_repository.delete_project(
        db, owner_id=owner_id, project_id=project_id
    )
    if not deleted:
        raise ProjectNotFoundError("Project not found.")
