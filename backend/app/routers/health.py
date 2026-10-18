"""Health-check router."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    app_name: str


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health_check() -> HealthResponse:
    """Returns 200 OK when the service is up."""
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        app_name=settings.app_name,
    )
