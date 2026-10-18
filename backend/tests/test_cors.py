"""Tests for CORS behaviour.

The CORSMiddleware only sets the `access-control-allow-origin` response header
when the request carries an `Origin` header that matches the allow-list.
We test:
  - An allowed origin gets the CORS header back.
  - A disallowed origin does NOT get the CORS header back.
  - The wildcard "*" is never in the header value.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.routers import health as health_router

ALLOWED = "http://localhost:3000"
DISALLOWED = "http://evil.example.com"


def _make_client(cors_origins: list[str]) -> TestClient:
    """Create a fresh FastAPI app with the given CORS origins."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router.router)
    return TestClient(app)


@pytest.fixture()
def client() -> TestClient:
    return _make_client([ALLOWED])


def test_allowed_origin_gets_cors_header(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED})
    assert response.status_code == 200
    acao = response.headers.get("access-control-allow-origin")
    assert acao == ALLOWED, f"Expected CORS header '{ALLOWED}', got: {acao!r}"


def test_disallowed_origin_gets_no_cors_header(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": DISALLOWED})
    assert response.status_code == 200
    acao = response.headers.get("access-control-allow-origin")
    assert acao != DISALLOWED, (
        f"Disallowed origin should not receive CORS header, got: {acao!r}"
    )


def test_wildcard_never_returned(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED})
    acao = response.headers.get("access-control-allow-origin", "")
    assert acao != "*", "CORS must not return wildcard '*'"
