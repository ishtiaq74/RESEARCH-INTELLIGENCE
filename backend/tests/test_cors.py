"""Tests for CORS behaviour.

The CORSMiddleware only sets the `access-control-allow-origin` response header
when the request carries an `Origin` header that matches the allow-list.

Tests:
  - A wildcard value in Settings raises a ValueError at startup.
  - An allowed origin gets its exact origin echoed back.
  - A disallowed origin gets no access-control-allow-origin header.
  - A preflight (OPTIONS) request from an allowed origin succeeds.
  - A preflight (OPTIONS) request from a disallowed origin gets no allow header.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ALLOWED = "http://localhost:3000"
DISALLOWED = "http://evil.example.com"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _client(cors_origins: str) -> TestClient:
    """Build a real app via create_app() with the given CORS origins string."""
    return TestClient(create_app(Settings(cors_origins=cors_origins)))


# ---------------------------------------------------------------------------
# T1.2e-2: Validation tests
# ---------------------------------------------------------------------------


def test_wildcard_origin_raises() -> None:
    """Settings must reject '*' as a CORS origin."""
    with pytest.raises(Exception, match=r"wildcard|\\*"):
        Settings(cors_origins="*")


def test_wildcard_in_list_raises() -> None:
    """Settings must reject '*' even when mixed with valid origins."""
    with pytest.raises(Exception, match=r"wildcard|\\*"):
        Settings(cors_origins="http://localhost:3000,*")


def test_empty_cors_origins_raises() -> None:
    """Settings must reject an empty CORS origins string."""
    with pytest.raises(Exception, match=r"empty"):
        Settings(cors_origins="  ,  ")


# ---------------------------------------------------------------------------
# T1.2e-2 & T1.2e-3: Runtime CORS header tests
# ---------------------------------------------------------------------------


def test_allowed_origin_gets_exact_origin_echoed() -> None:
    """An allowed origin must receive its own origin, not '*'."""
    client = _client(ALLOWED)
    response = client.get("/health", headers={"Origin": ALLOWED})
    assert response.status_code == 200
    acao = response.headers.get("access-control-allow-origin")
    assert acao == ALLOWED, f"Expected CORS header '{ALLOWED}', got: {acao!r}"


def test_disallowed_origin_gets_no_cors_header() -> None:
    """A disallowed origin must not receive an access-control-allow-origin header."""
    client = _client(ALLOWED)
    response = client.get("/health", headers={"Origin": DISALLOWED})
    assert response.status_code == 200
    acao = response.headers.get("access-control-allow-origin")
    assert acao is None or acao != DISALLOWED, (
        f"Disallowed origin should not receive CORS header, got: {acao!r}"
    )


def test_wildcard_never_returned() -> None:
    """The CORS header value must never be the wildcard '*'."""
    client = _client(ALLOWED)
    response = client.get("/health", headers={"Origin": ALLOWED})
    acao = response.headers.get("access-control-allow-origin", "")
    assert acao != "*", "CORS must not return wildcard '*'"


def test_preflight_allowed_origin_succeeds() -> None:
    """OPTIONS preflight from an allowed origin must return 200."""
    client = _client(ALLOWED)
    response = client.options(
        "/health",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    acao = response.headers.get("access-control-allow-origin")
    assert acao == ALLOWED, f"Preflight allowed origin expected '{ALLOWED}', got: {acao!r}"


def test_preflight_disallowed_origin_gets_no_allow_header() -> None:
    """OPTIONS preflight from a disallowed origin must not return an allow header."""
    client = _client(ALLOWED)
    response = client.options(
        "/health",
        headers={
            "Origin": DISALLOWED,
            "Access-Control-Request-Method": "GET",
        },
    )
    acao = response.headers.get("access-control-allow-origin")
    assert acao is None or acao != DISALLOWED, (
        f"Preflight for disallowed origin should not return allow header, got: {acao!r}"
    )
