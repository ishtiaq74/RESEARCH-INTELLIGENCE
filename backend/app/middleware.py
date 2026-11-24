"""Application middlewares for security, isolation, and error handling."""
from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings, settings

logger = logging.getLogger("app.errors")

# ---------------------------------------------------------------------------
# Upload size guard (pure ASGI, NOT BaseHTTPMiddleware)
# ---------------------------------------------------------------------------

# Constant added to max_upload_bytes to cover multipart framing (boundaries,
# headers, CRLF separators). Chosen conservatively: a multipart boundary is at
# most 70 bytes, field headers are well under 1 KiB, so 4 KiB is generous.
_MULTIPART_OVERHEAD_BYTES: int = 4 * 1024

# Exact path shape for document upload: POST /projects/{project_id}/documents
_UPLOAD_PATH_RE = re.compile(r"^/projects/[^/]+/documents$")


class _BodyTooLarge(Exception):
    """Internal sentinel raised when streamed request bytes exceed the limit."""


def _is_upload_post(scope: Scope) -> bool:
    """Return True when the request is POST to /projects/{id}/documents."""
    path = scope.get("path")
    return (
        scope["type"] == "http"
        and scope["method"] == "POST"
        and isinstance(path, str)
        and _UPLOAD_PATH_RE.match(path) is not None
    )


async def _send_413(send: Send, detail: str) -> None:
    """Send a minimal ASGI HTTP 413 response with a JSON body."""
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


class UploadSizeGuard:
    """Pure ASGI middleware that rejects oversized uploads before the route runs.

    WHY PURE ASGI (not BaseHTTPMiddleware):
      Starlette's BaseHTTPMiddleware calls `request.body()` which reads the entire
      body into memory before passing control to the route handler, or buffers via
      an internal task group. For multipart uploads Starlette also spools parts to
      temp files before any route code executes, so a size check inside the route
      handler is too late — the disk write has already occurred.

      By intercepting the raw ASGI `receive` channel we:
        1. Check the Content-Length header first and reject immediately (zero bytes read).
        2. Count bytes as they stream in; abort as soon as the limit is exceeded
           without buffering the full body in memory or spooling past the limit.

    WHY 413 STILL GETS CORS AND CACHE-CONTROL HEADERS:
      This middleware sits innermost (wrapping FastAPI directly), inside
      ErrorHandlingMiddleware, OriginCheckMiddleware, CacheControlMiddleware,
      and CORSMiddleware (outermost). Because CacheControlMiddleware and
      CORSMiddleware wrap it, their response-phase processing runs on the 413
      response and attaches `Cache-Control: no-store` and CORS headers. Meanwhile
      OriginCheckMiddleware sits outside it, rejecting disallowed Origins with
      403 before any body bytes are read.

    Coverage: POST /projects/{id}/documents only. All other paths pass through.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_upload_post(scope):
            await self._app(scope, receive, send)
            return

        limit = self._max_bytes + _MULTIPART_OVERHEAD_BYTES
        headers: dict[bytes, bytes] = {
            k.lower(): v for k, v in scope.get("headers", [])
        }
        content_length_raw = headers.get(b"content-length")
        if content_length_raw is not None:
            try:
                cl = int(content_length_raw)
            except ValueError:
                cl = 0
            if cl > limit:
                await _send_413(send, "Upload too large.")
                return

        seen = 0
        too_large = False
        downstream_started = False

        async def guarded_send(message: Any) -> None:
            nonlocal downstream_started
            if too_large and not downstream_started:
                # Suppress any 400/500 frame the inner framework attempts to emit
                # when aborting the stream after exceeding the upload limit.
                return
            if message["type"] == "http.response.start":
                downstream_started = True
            await send(message)

        async def counting_receive() -> Any:
            nonlocal seen, too_large
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    too_large = True
                    raise _BodyTooLarge()
            return message

        with contextlib.suppress(_BodyTooLarge):
            await self._app(scope, counting_receive, guarded_send)

        if too_large and not downstream_started:
            await _send_413(send, "Upload too large.")


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


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Ensure sensitive authentication and user data endpoints are never cached.

    WHY NO-STORE ON /auth AND /projects:
      Responses containing user information, session state, project metadata,
      and authentication errors contain sensitive user-specific data that must
      never be cached by shared proxies, CDNs, or browser caches.
      Setting Cache-Control: no-store instructs clients and intermediaries
      never to store or reuse these responses.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/auth") or path.startswith("/projects"):
            response.headers["Cache-Control"] = "no-store"
        return response


