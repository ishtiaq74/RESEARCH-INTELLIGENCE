"""Tests for the /health endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body() -> None:
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "app_name" in data
