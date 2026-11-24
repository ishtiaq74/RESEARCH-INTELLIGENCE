"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.config import settings as _default_settings
from app.middleware import (
    CacheControlMiddleware,
    ErrorHandlingMiddleware,
    OriginCheckMiddleware,
    UploadSizeGuard,
)
from app.routers import auth, documents, health, projects


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
    app.state.settings = cfg

    # T2 CORS change: allow_credentials=True required for session cookies.
    #
    # WHY allow_credentials=True NOW:
    #   The browser will not send cookies with cross-origin requests unless
    #   the server responds with Access-Control-Allow-Credentials: true.
    #   The frontend (http://localhost:3000) is a different origin from the
    #   backend (http://localhost:8000), so cookies require this flag.
    #
    # WHY THIS IS SAFE WITH EXPLICIT ORIGINS:
    #   allow_credentials=True combined with allow_origins=["*"] is rejected
    #   by browsers — they refuse to expose the response.  Our no-wildcard
    #   validator (field_validator on cors_origins) ensures "*" can never appear
    #   in the origins list, so this combination is structurally impossible here.
    #
    # WHY POST, DELETE, AND PATCH ARE NOW INCLUDED:
    #   The auth endpoints use POST (/register, /login, /logout), and the
    #   projects endpoints use GET, POST, DELETE, and PATCH.
    # Starlette add_middleware wraps in reverse order (user_middleware.insert(0, ...)):
    # Middlewares added later become OUTER.
    # Order from inner to outer:
    #   1. UploadSizeGuard (pure ASGI; rejects oversized POSTs before Starlette spools)
    #   2. ErrorHandlingMiddleware (catches unhandled exceptions, returns JSON 500)
    #   3. OriginCheckMiddleware (enforces allowed origins for state-changing methods)
    #   4. CacheControlMiddleware (sets Cache-Control: no-store on /auth and /projects)
    #   5. CORSMiddleware (outermost: attaches CORS headers, handles preflight)
    #
    # WHY UploadSizeGuard IS INNERMOST (INSIDE ErrorHandling AND OriginCheck):
    #   Starlette spools multipart bodies to temp files BEFORE the route handler runs,
    #   so a size check inside the route is too late. UploadSizeGuard intercepts the
    #   raw ASGI receive channel directly around FastAPI and counts bytes as they
    #   stream in, without a BaseHTTPMiddleware task-group boundary between receive
    #   and the guard. It is placed inside OriginCheckMiddleware so that an upload
    #   from a disallowed Origin is rejected with 403 before reading any bytes.
    #   Its 413 responses still pass through CacheControlMiddleware and CORSMiddleware
    #   and therefore carry the correct Cache-Control: no-store and CORS headers.
    app.add_middleware(UploadSizeGuard, max_bytes=cfg.max_upload_bytes)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(OriginCheckMiddleware, settings=cfg)
    app.add_middleware(CacheControlMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(documents.router)

    return app


app = create_app()
