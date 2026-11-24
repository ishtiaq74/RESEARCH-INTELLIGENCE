"""Tests for document upload settings in app.config."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import BACKEND_DIR, Settings


def test_upload_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify default values for upload settings."""
    # Ensure no environment variables interfere
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


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("max_upload_bytes", 0),
        ("max_upload_bytes", -1),
        ("max_pdf_pages", 0),
        ("max_pdf_pages", -10),
        ("max_documents_per_project", 0),
        ("max_documents_per_project", -5),
        ("pdf_probe_timeout_seconds", 0.0),
        ("pdf_probe_timeout_seconds", -0.5),
    ],
)
def test_upload_settings_zero_and_negative_rejected(field: str, invalid_value: int | float) -> None:
    """Verify zero and negative values are rejected with ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, **{field: invalid_value})
    assert "must be greater than zero" in str(exc_info.value)
