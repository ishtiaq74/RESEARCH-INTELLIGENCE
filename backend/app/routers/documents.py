"""Documents router: upload and manage research PDF documents within projects.

All endpoints require authentication (require_current_user dependency).
All data access goes through document_service, which always filters by
owner_id so one user can never see or modify another user's documents.

Routes
------
POST   /projects/{project_id}/documents              — upload a PDF document
GET    /projects/{project_id}/documents              — list documents in a project
GET    /projects/{project_id}/documents/{doc_id}     — get one document
DELETE /projects/{project_id}/documents/{doc_id}     — delete a document

WHY 404 INSTEAD OF 403 FOR CROSS-USER ACCESS:
  Returning 403 on a document or project owned by another user would reveal that
  the resource exists. Returning 404 hides that information — the caller cannot
  distinguish "does not exist" from "belongs to someone else".

WHY DocumentRead EXCLUDES stored_filename, sha256, AND path:
  These are internal implementation details (on-disk UUID filename, content hash,
  filesystem path). Exposing them would reveal storage layout, enable enumeration
  of content, and leak internal path structures. The response schema exposes only
  the user-facing metadata fields.
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import Settings
from app.config import settings as _default_settings
from app.db.session import get_db
from app.dependencies import require_current_user
from app.models.user import User
from app.services import document_service
from app.services.document_service import DocumentError
from app.services.project_service import ProjectNotFoundError

router = APIRouter(prefix="/projects", tags=["documents"])

_MAX_SQLITE_INT: int = 2**63 - 1
_MAX_OFFSET: int = 1_000_000


def _get_cfg(request: Request) -> Settings:
    """Extract the Settings instance from app state, falling back to the global singleton."""
    cfg = getattr(request.app.state, "settings", None)
    return cfg if isinstance(cfg, Settings) else _default_settings


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class DocumentRead(BaseModel):
    """Public representation of an uploaded document.

    Intentionally excludes stored_filename, sha256, and any filesystem path —
    those are internal storage implementation details (see module docstring).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    original_filename: str
    size_bytes: int
    page_count: int | None
    status: str
    created_at: datetime.datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/documents",
    status_code=201,
    response_model=DocumentRead,
)
def upload_document(
    request: Request,
    project_id: int = Path(..., ge=1, le=_MAX_SQLITE_INT),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> DocumentRead:
    """Upload a PDF document into the project.

    Returns 201 with the created document on success.
    Returns 401 if not authenticated.
    Returns 404 if the project does not exist or belongs to another user.
    Returns 409 if an identical document (same SHA-256) already exists in the project.
    Returns 413 if the uploaded file exceeds the size limit.
    Returns 415 if the file is not a PDF.
    Returns 422 if the PDF is corrupt, encrypted, empty, or has too many pages,
              or if the project has reached its document limit.
    """
    cfg = _get_cfg(request)
    try:
        doc = document_service.create_document(
            db,
            owner_id=current_user.id,
            project_id=project_id,
            stream=file.file,
            filename=file.filename,
            cfg=cfg,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return DocumentRead.model_validate(doc)


@router.get(
    "/{project_id}/documents",
    response_model=list[DocumentRead],
)
def list_documents(
    project_id: int = Path(..., ge=1, le=_MAX_SQLITE_INT),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=_MAX_OFFSET),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> list[DocumentRead]:
    """Return all documents in the project (ordered by id ascending).

    Returns 401 if not authenticated.
    Returns 404 if the project does not exist or belongs to another user.
    Returns 422 if pagination parameters are out of range.
    """
    try:
        docs = document_service.list_documents(
            db,
            owner_id=current_user.id,
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return [DocumentRead.model_validate(d) for d in docs]


@router.get(
    "/{project_id}/documents/{document_id}",
    response_model=DocumentRead,
)
def get_document(
    project_id: int = Path(..., ge=1, le=_MAX_SQLITE_INT),
    document_id: int = Path(..., ge=1, le=_MAX_SQLITE_INT),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> DocumentRead:
    """Return a single document.

    Returns 401 if not authenticated.
    Returns 404 if the project or document does not exist or belongs to another user.
    """
    try:
        doc = document_service.get_document(
            db,
            owner_id=current_user.id,
            project_id=project_id,
            document_id=document_id,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return DocumentRead.model_validate(doc)


@router.delete(
    "/{project_id}/documents/{document_id}",
    status_code=204,
)
def delete_document(
    request: Request,
    project_id: int = Path(..., ge=1, le=_MAX_SQLITE_INT),
    document_id: int = Path(..., ge=1, le=_MAX_SQLITE_INT),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> None:
    """Delete a document and its stored file.

    Returns 204 on success.
    Returns 401 if not authenticated.
    Returns 404 if the project or document does not exist or belongs to another user.
    """
    cfg = _get_cfg(request)
    try:
        document_service.delete_document(
            db,
            owner_id=current_user.id,
            project_id=project_id,
            document_id=document_id,
            cfg=cfg,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
