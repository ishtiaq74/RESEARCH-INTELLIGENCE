"""Tests for app.services.pdf_probe (subprocess PDF inspection).

PDF fixtures are generated with pypdf inside the tests, so no binary files are committed.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.services.pdf_probe import PdfProbeError, probe_pdf


def make_pdf_bytes(pages: int = 1, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if password is not None:
        # RC4 is used only to build a test fixture; it needs no extra packages.
        writer.encrypt(password, algorithm="RC4-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_valid_pdf_reports_page_count(tmp_path: Path) -> None:
    result = probe_pdf(write(tmp_path / "ok.pdf", make_pdf_bytes(pages=3)))
    assert result.is_encrypted is False
    assert result.page_count == 3


def test_zero_page_pdf_reports_zero(tmp_path: Path) -> None:
    result = probe_pdf(write(tmp_path / "empty.pdf", make_pdf_bytes(pages=0)))
    assert result.is_encrypted is False
    assert result.page_count == 0


def test_encrypted_pdf_is_reported_without_decrypting(tmp_path: Path) -> None:
    result = probe_pdf(write(tmp_path / "enc.pdf", make_pdf_bytes(pages=2, password="secret")))
    assert result.is_encrypted is True
    assert result.page_count is None


def test_garbage_file_is_corrupt(tmp_path: Path) -> None:
    path = write(tmp_path / "junk.pdf", b"%PDF-1.7\nthis is not a real pdf at all\x00\x01\x02")
    with pytest.raises(PdfProbeError) as info:
        probe_pdf(path)
    assert info.value.reason == "corrupt"


def test_missing_file_is_corrupt(tmp_path: Path) -> None:
    with pytest.raises(PdfProbeError) as info:
        probe_pdf(tmp_path / "does-not-exist.pdf")
    assert info.value.reason == "corrupt"


def test_timeout_is_reported_as_timeout(tmp_path: Path) -> None:
    path = write(tmp_path / "ok.pdf", make_pdf_bytes())
    # Starting a Python process always takes longer than 1 ms, so this must time out.
    with pytest.raises(PdfProbeError) as info:
        probe_pdf(path, timeout_s=0.001)
    assert info.value.reason == "timeout"
