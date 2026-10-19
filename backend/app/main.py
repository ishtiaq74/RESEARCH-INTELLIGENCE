"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.config import settings as _default_settings
from app.routers import health


def create_app(cfg: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        cfg: Settings instance to use. Defaults to the global settings singleton.
             Pass an explicit Settings() in tests to avoid touching the .env file.
    """
    cfg = cfg or _default_settings

    app = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        debug=cfg.debug,
    )

    # T2 will revisit allow_methods and allow_headers when auth is designed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(health.router)

    return app


app = create_app()
