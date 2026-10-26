"""Projects router: CRUD endpoints for research projects.

All endpoints require authentication (require_current_user dependency).
All data access goes through project_repository, which always filters by
owner_id so one user can never see or modify another user's projects.

Routes
------
POST   /projects           — create a project
GET    /projects           — list the caller's projects
GET    /projects/{id}      — get one project (404 if not found or not owned)
PATCH  /projects/{id}      — rename a project (404 if not found or not owned)
DELETE /projects/{id}      — delete a project (404 if not found or not owned)

WHY 404 INSTEAD OF 403 FOR CROSS-USER ACCESS:
  Returning 403 on a project owned by another user would reveal that the
  project exists.  Returning 404 hides that information — the caller cannot
  distinguish "project does not exist" from "project belongs to someone else".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_current_user
from app.models.user import User
from app.repositories.project_repository import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class UpdateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class ProjectResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, project: object) -> ProjectResponse:
        from app.models.project import Project as ProjectModel

        p: ProjectModel = project  # type: ignore[assignment]
        return cls(
            id=p.id,
            name=p.name,
            owner_id=p.owner_id,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ProjectResponse, status_code=201)
def create(
    body: CreateProjectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ProjectResponse:
    """Create a new project owned by the current user.

    Returns 201 with the created project on success.
    Returns 401 if not authenticated.
    Returns 422 if name is empty or exceeds 200 characters.
    """
    project = create_project(db, owner_id=current_user.id, name=body.name)
    return ProjectResponse.from_orm_model(project)


@router.get("", response_model=list[ProjectResponse])
def list_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> list[ProjectResponse]:
    """Return all projects owned by the current user (ordered by id)."""
    projects = list_projects(db, owner_id=current_user.id)
    return [ProjectResponse.from_orm_model(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_one(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ProjectResponse:
    """Return a single project.

    Returns 404 if the project does not exist or belongs to another user.
    (WHY 404 not 403: see module docstring.)
    """
    project = get_project(db, owner_id=current_user.id, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectResponse.from_orm_model(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update(
    project_id: int,
    body: UpdateProjectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ProjectResponse:
    """Rename a project.

    Returns 404 if the project does not exist or belongs to another user.
    Returns 422 if name is empty or exceeds 200 characters.
    """
    project = update_project(
        db,
        owner_id=current_user.id,
        project_id=project_id,
        name=body.name,
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectResponse.from_orm_model(project)


@router.delete("/{project_id}", status_code=204)
def delete(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> None:
    """Delete a project.

    Returns 204 on success.
    Returns 404 if the project does not exist or belongs to another user.
    """
    deleted = delete_project(db, owner_id=current_user.id, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found.")
