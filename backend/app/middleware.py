"""Application middlewares for security, isolation, and error handling."""
from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import Settings, settings


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
