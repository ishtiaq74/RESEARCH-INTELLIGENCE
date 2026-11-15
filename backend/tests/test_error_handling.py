"""Tests for unhandled error handling and CORS propagation (T2.4-fixes Step 3).

Verifies that unhandled exceptions return a uniform JSON 500 {"detail": "Internal server error."},
log tracebacks via the standard logging module, never leak tracebacks to clients,
and correctly retain CORS headers so browsers receive HTTP 500 rather than a CORS error.
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_unhandled_error_returns_json_500_with_cors_headers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unhandled error returns JSON 500 with CORS headers and logs traceback."""
    app = create_app(
        Settings(
            cors_origins="http://localhost:3000",
            debug=False,
        )
    )

    # Attach a test-only route that raises an unhandled exception
    @app.get("/test-unhandled-crash")
    def crash_endpoint() -> None:
        raise RuntimeError("Deliberate unhandled failure")

    client = TestClient(app, raise_server_exceptions=False)

    logger = logging.getLogger("app.errors")
    logger.disabled = False
    caplog.set_level(logging.ERROR, logger="app.errors")
    response = client.get(
        "/test-unhandled-crash",
        headers={"Origin": "http://localhost:3000"},
    )

    # Status must be 500
    assert response.status_code == 500

    # Body must be strict JSON without traceback
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Internal server error."}
    assert "Deliberate unhandled failure" not in response.text
    assert "Traceback" not in response.text

    # CORS header must be present because CORSMiddleware is outer
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"

    # Standard logging must have captured the exception
    assert "Unhandled server exception" in caplog.text
    assert "Deliberate unhandled failure" in caplog.text


def test_debug_false_leaks_no_traceback() -> None:
    """Confirm debug=False produces no traceback in response body."""
    app = create_app(
        Settings(
            cors_origins="http://localhost:3000",
            debug=False,
        )
    )

    @app.post("/test-post-crash")
    def post_crash() -> None:
        raise ValueError("Secret database credentials or path leaking test")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/test-post-crash",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert "Secret database credentials" not in response.text
