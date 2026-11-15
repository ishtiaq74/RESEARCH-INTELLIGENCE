"""Application middlewares for security, isolation, and error handling."""
from __future__ import annotations

import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import Settings, settings

logger = logging.getLogger("app.errors")


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Enforce origin checks on state-changing HTTP requests.

    WHY AN EXPLICIT ORIGIN CHECK:
      SameSite=Lax cookies are sent with same-site requests, but "same-site"
      is broader than "same-origin" (e.g. another port or subdomain on localhost
      or the same domain counts as same-site). Furthermore, a simple POST (such
      as text/plain or multipart form) can be sent cross-origin without a CORS
      preflight. While CORS prevents the browser from reading the response, it
      does not prevent the server handler from executing.
      Checking the Origin header on all state-changing methods (POST, PUT, PATCH,
      DELETE) ensures requests originating from unauthorized browser origins are
      rejected with 403 before any route handler executes.
      Requests without an Origin header (e.g., non-browser API clients, tests,
      or server-to-server calls) are permitted.
    """

    def __init__(self, app: Any, settings: Settings | None = None) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin is not None:
                app_settings = getattr(request.app.state, "settings", None)
                cfg: Settings = self._settings or (
                    app_settings if isinstance(app_settings, Settings) else settings
                )
                if origin not in cfg.cors_origins_list:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Origin not allowed."},
                    )

        return await call_next(request)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions, log the traceback, and return JSON 500 with CORS.

    WHY AN INNER ERROR MIDDLEWARE:
      Starlette's default ServerErrorMiddleware sits outside CORSMiddleware.
      When an unhandled exception bubbles up to ServerErrorMiddleware, it generates
      a plain 500 response that never passes through CORSMiddleware, omitting
      the Access-Control-Allow-Origin header and causing the browser to report a
      CORS error rather than an HTTP 500.
      By catching unhandled exceptions inside CORSMiddleware, we:
        1. Log the full traceback using standard logging (logger.exception).
        2. Return a safe, uniform JSON 500 response {"detail": "Internal server error."}.
        3. Never leak internal tracebacks to the client, even in debug mode.
        4. Allow CORSMiddleware (which is outermost) to attach CORS headers so
           the browser accurately receives and reports HTTP 500 to the client application.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled server exception processing %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error."},
            )

