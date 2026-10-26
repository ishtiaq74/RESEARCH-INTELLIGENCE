"""Project repository — all DB access for the projects table lives here.

WHY OWNERSHIP BELONGS IN THE DATA LAYER AND NOT ONLY IN THE ROUTER:
  If ownership were enforced only in routers, any internal caller — a service,
  a background job, a future endpoint added by a developer who forgets to
  add the check — could silently access another user's data.  The router
  cannot be the last line of defense because it is bypassed by every non-HTTP
  call path.

  Putting owner_id in every query in this module means the filter is
  structurally impossible to omit: there is literally no function that fetches
  a project by id alone.  The worst-case developer mistake then becomes a
  runtime error ("owner_id missing"), not a data-leak.

  This mirrors the design rationale in user_repository.py and AGENT_RULES.md
  ("Every query touching user data must be filtered by the owner and project
  on the server side").
"""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from app.models.project import Project


def create_project(db: Session, owner_id: int, name: str) -> Project:
    """Insert a new project row owned by owner_id and return it.

    Both created_at and updated_at are set to the current UTC time.
    """
    now = datetime.datetime.now(datetime.UTC)
    project = Project(
        owner_id=owner_id,
        name=name,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session, owner_id: int) -> list[Project]:
    """Return all projects owned by owner_id, ordered by id ascending."""
    return (
        db.query(Project)
        .filter(Project.owner_id == owner_id)
        .order_by(Project.id)
        .all()
    )


def get_project(db: Session, owner_id: int, project_id: int) -> Project | None:
    """Return the project with the given id that is owned by owner_id, or None.

    WHY BOTH owner_id AND project_id IN THE FILTER:
      Filtering by id alone would return the row regardless of ownership,
      exposing other users' projects to any authenticated caller.  The AND
      condition ensures the row is only returned when *both* conditions hold.
    """
    return (
        db.query(Project)
        .filter(Project.owner_id == owner_id, Project.id == project_id)
        .first()
    )


def update_project(
    db: Session,
    owner_id: int,
    project_id: int,
    name: str,
) -> Project | None:
    """Rename the project if it exists and is owned by owner_id.

    Returns the updated Project, or None if not found / not owned.
    updated_at is refreshed to the current UTC time.
    """
    project = get_project(db, owner_id, project_id)
    if project is None:
        return None
    project.name = name
    project.updated_at = datetime.datetime.now(datetime.UTC)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, owner_id: int, project_id: int) -> bool:
    """Delete the project if it exists and is owned by owner_id.

    Returns True if a row was deleted, False if not found / not owned.
    """
    project = get_project(db, owner_id, project_id)
    if project is None:
        return False
    db.delete(project)
    db.commit()
    return True
