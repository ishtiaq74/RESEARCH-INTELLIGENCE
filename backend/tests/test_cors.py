"""Tests for CORS behaviour.

T1.2e-2: wildcard and empty values raise ValueError at Settings construction time.
T1.2e-3 (updated for T2): allow_credentials=True, methods now include POST and DELETE.

T2 CORS change rationale (documented in app/main.py):
  Session cookies require allow_credentials=True.  The browser will not send
  cookies on cross-origin requests unless the server returns
  Access-Control-Allow-Credentials: true.  This is only safe with explicit origins
  (never wildcard), which the existing field_validator enforces.

Tests:
  - Wildcard origin raises ValueError.
  - Wildcard-in-list raises ValueError.
  - Empty string raises ValueError (covers the no-wildcard validator).
  - Allowed origin receives its exact origin echoed back.
  - Disallowed origin receives no Access-Control-Allow-Origin header.
  - The wildcard '*' is never returned.
  - Allowed origin receives Access-Control-Allow-Credentials: true (T2 new).
  - POST preflight from an allowed origin succeeds (T2 new).
  - POST preflight from a disallowed origin gets no allow header (T2 new).
  - GET preflight from an allowed origin succeeds.
  - GET preflight from a disallowed origin gets no allow header.
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
# T1.2e-2: Validation tests (unchanged from T1)
# ---------------------------------------------------------------------------


def test_wildcard_origin_raises() -> None:
    """Settings must reject '*' as a CORS origin."""
    with pytest.raises(Exception, match=r"wildcard|\*"):
        Settings(cors_origins="*")


def test_wildcard_in_list_raises() -> None:
    """Settings must reject '*' even when mixed with valid origins."""
    with pytest.raises(Exception, match=r"wildcard|\*"):
        Settings(cors_origins="http://localhost:3000,*")


def test_empty_cors_origins_raises() -> None:
    """Settings must reject an empty CORS origins string."""
    with pytest.raises(Exception, match=r"empty"):
        Settings(cors_origins="  ,  ")


# ---------------------------------------------------------------------------
# Runtime CORS header tests
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


def test_allowed_origin_gets_credentials_header() -> None:
    """T2: allowed origin must receive Access-Control-Allow-Credentials: true.

    WHY THIS MATTERS:
      allow_credentials=True makes the server include the ACAC header.
      Without it the browser strips cookies from the cross-origin response and
      will not attach them on the next request — sessions would break entirely
      for the frontend on a different port (localhost:3000 vs :8000).
    """
    client = _client(ALLOWED)
    response = client.get("/health", headers={"Origin": ALLOWED})
    acac = response.headers.get("access-control-allow-credentials")
    assert acac == "true", (
        f"Expected Access-Control-Allow-Credentials: true, got: {acac!r}"
    )


# ---------------------------------------------------------------------------
# Preflight (OPTIONS) tests — GET method (T1 behaviour preserved)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Preflight (OPTIONS) tests — POST method (T2 new: auth endpoints use POST)
# ---------------------------------------------------------------------------


def test_post_preflight_allowed_origin_succeeds() -> None:
    """T2: OPTIONS preflight for POST from an allowed origin must succeed.

    The auth endpoints (register, login, logout) use POST.  Without POST in
    allow_methods the browser's preflight would fail and the auth calls would
    be blocked entirely.
    """
    client = _client(ALLOWED)
    response = client.options(
        "/auth/login",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    acao = response.headers.get("access-control-allow-origin")
    assert acao == ALLOWED, f"POST preflight allowed origin expected '{ALLOWED}', got: {acao!r}"


def test_post_preflight_disallowed_origin_gets_no_allow_header() -> None:
    """T2: OPTIONS preflight for POST from a disallowed origin must not be allowed."""
    client = _client(ALLOWED)
    response = client.options(
        "/auth/login",
        headers={
            "Origin": DISALLOWED,
            "Access-Control-Request-Method": "POST",
        },
    )
    acao = response.headers.get("access-control-allow-origin")
    assert acao is None or acao != DISALLOWED, (
        f"POST preflight for disallowed origin should not return allow header, got: {acao!r}"
    )


def test_patch_preflight_allowed_origin_succeeds() -> None:
    """T2.2: OPTIONS preflight for PATCH from an allowed origin must succeed."""
    client = _client(ALLOWED)
    response = client.options(
        "/projects/1",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "PATCH",
        },
    )
    assert response.status_code == 200
    acao = response.headers.get("access-control-allow-origin")
    assert acao == ALLOWED, f"PATCH preflight allowed origin expected '{ALLOWED}', got: {acao!r}"


def test_no_set_cookie_in_expose_headers() -> None:
    """Set-Cookie must NOT be exposed in Access-Control-Expose-Headers.

    Per WHATWG Fetch standard (Section 2.2), Set-Cookie is a forbidden
    response-header name and browsers never expose it to client-side JavaScript.
    """
    client = _client(ALLOWED)
    response = client.get("/health", headers={"Origin": ALLOWED})
    aceh = response.headers.get("access-control-expose-headers", "")
    assert "set-cookie" not in aceh.lower(), (
        f"Set-Cookie must not be in Access-Control-Expose-Headers, got: {aceh!r}"
    )
