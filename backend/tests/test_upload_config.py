"""Tests for document upload settings in app.config."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import BACKEND_DIR, Settings


def test_upload_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify default values for upload settings."""
    monkeypatch.delenv("MAX_UPLOAD_BYTES", raising=False)
    monkeypatch.delenv("MAX_PDF_PAGES", raising=False)
    monkeypatch.delenv("MAX_DOCUMENTS_PER_PROJECT", raising=False)
    monkeypatch.delenv("PDF_PROBE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("UPLOAD_DIR", raising=False)

    s = Settings(_env_file=None)
    assert s.max_upload_bytes == 20 * 1024 * 1024
    assert s.max_pdf_pages == 300
    assert s.max_documents_per_project == 20
    assert s.pdf_probe_timeout_seconds == 10.0
    assert s.upload_dir == BACKEND_DIR / "data" / "uploads"


def test_upload_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify upload settings can be overridden via environment variables."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10485760")
    monkeypatch.setenv("MAX_PDF_PAGES", "150")
    monkeypatch.setenv("MAX_DOCUMENTS_PER_PROJECT", "10")
    monkeypatch.setenv("PDF_PROBE_TIMEOUT_SECONDS", "5.5")
    monkeypatch.setenv("UPLOAD_DIR", "custom/upload/path")

    s = Settings(_env_file=None)
    assert s.max_upload_bytes == 10485760
    assert s.max_pdf_pages == 150
    assert s.max_documents_per_project == 10
    assert s.pdf_probe_timeout_seconds == 5.5
    assert s.upload_dir == Path("custom/upload/path")


@pytest.mark.parametrize("invalid_value", [0, -1])
def test_upload_settings_max_upload_bytes_rejected(invalid_value: int) -> None:
    """Verify zero and negative max_upload_bytes are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, max_upload_bytes=invalid_value)
    assert "must be greater than zero" in str(exc_info.value)


@pytest.mark.parametrize("invalid_value", [0, -10])
def test_upload_settings_max_pdf_pages_rejected(invalid_value: int) -> None:
    """Verify zero and negative max_pdf_pages are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, max_pdf_pages=invalid_value)
    assert "must be greater than zero" in str(exc_info.value)


@pytest.mark.parametrize("invalid_value", [0, -5])
def test_upload_settings_max_documents_rejected(invalid_value: int) -> None:
    """Verify zero and negative max_documents_per_project are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, max_documents_per_project=invalid_value)
    assert "must be greater than zero" in str(exc_info.value)


@pytest.mark.parametrize("invalid_value", [0.0, -0.5])
def test_upload_settings_timeout_rejected(invalid_value: float) -> None:
    """Verify zero and negative pdf_probe_timeout_seconds are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, pdf_probe_timeout_seconds=invalid_value)
    assert "must be greater than zero" in str(exc_info.value)
