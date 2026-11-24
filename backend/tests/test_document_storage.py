"""Tests for app.services.document_storage (validation and safe storage of PDFs)."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.services.document_storage import (
    StorageError,
    StoredFile,
    delete_project_files,
    delete_stored_file,
    sanitize_display_name,
    store_pdf,
    stored_file_path,
)

MAX_BYTES = 1_000_000
MAX_PAGES = 5


def make_pdf_bytes(pages: int = 1, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if password is not None:
        writer.encrypt(password, algorithm="RC4-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def store(
    upload_dir: Path,
    data: bytes,
    *,
    filename: str | None = "paper.pdf",
    project_id: int = 7,
    max_bytes: int = MAX_BYTES,
    max_pages: int = MAX_PAGES,
) -> StoredFile:
    return store_pdf(
        io.BytesIO(data),
        upload_dir=upload_dir,
        project_id=project_id,
        filename=filename,
        max_bytes=max_bytes,
        max_pages=max_pages,
    )


def all_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


# --- success ---------------------------------------------------------------


def test_valid_pdf_is_stored_under_uuid_name(tmp_path: Path) -> None:
    data = make_pdf_bytes(pages=2)
    stored = store(tmp_path, data)

    assert stored.page_count == 2
    assert stored.size_bytes == len(data)
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert stored.display_name == "paper.pdf"
    assert stored.path == (tmp_path / "7" / stored.stored_filename).resolve()
    assert stored.path.read_bytes() == data
    assert len(stored.stored_filename) == 36  # 32 hex characters + ".pdf"
    assert not (tmp_path / ".tmp").exists() or not list((tmp_path / ".tmp").iterdir())


def test_file_exactly_at_size_limit_is_accepted(tmp_path: Path) -> None:
    data = make_pdf_bytes()
    stored = store(tmp_path, data, max_bytes=len(data))
    assert stored.size_bytes == len(data)


def test_two_uploads_get_different_stored_names(tmp_path: Path) -> None:
    data = make_pdf_bytes()
    first = store(tmp_path, data)
    second = store(tmp_path, data)
    assert first.stored_filename != second.stored_filename


# --- rejections: nothing may remain on disk ----------------------------------


def test_too_large_is_rejected_and_cleaned_up(tmp_path: Path) -> None:
    data = make_pdf_bytes()
    with pytest.raises(StorageError) as info:
        store(tmp_path, data, max_bytes=len(data) - 1)
    assert info.value.code == "too_large"
    assert all_files(tmp_path) == []


def test_oversize_stream_is_cut_off_early(tmp_path: Path) -> None:
    class CountingStream(io.BytesIO):
        def __init__(self) -> None:
            super().__init__(b"%PDF-" + b"0" * (10 * 1024 * 1024))
            self.bytes_read = 0

        def read(self, size: int | None = -1) -> bytes:
            chunk = super().read(size)
            self.bytes_read += len(chunk)
            return chunk

    stream = CountingStream()
    with pytest.raises(StorageError) as info:
        store_pdf(
            stream,
            upload_dir=tmp_path,
            project_id=1,
            filename="big.pdf",
            max_bytes=2 * 1024 * 1024,
            max_pages=MAX_PAGES,
        )
    assert info.value.code == "too_large"
    assert stream.bytes_read < 5 * 1024 * 1024  # stopped long before the end
    assert all_files(tmp_path) == []


def test_text_file_is_not_a_pdf(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        store(tmp_path, b"just some text, not a pdf", filename="paper.pdf")
    assert info.value.code == "not_pdf"
    assert all_files(tmp_path) == []


def test_empty_file_is_not_a_pdf(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        store(tmp_path, b"")
    assert info.value.code == "not_pdf"
    assert all_files(tmp_path) == []


def test_tiny_file_shorter_than_magic_is_not_a_pdf(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        store(tmp_path, b"%PD")
    assert info.value.code == "not_pdf"
    assert all_files(tmp_path) == []


def test_pdf_header_with_garbage_body_is_corrupt(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        store(tmp_path, b"%PDF-1.7\n" + b"garbage" * 50)
    assert info.value.code == "corrupt"
    assert all_files(tmp_path) == []


def test_encrypted_pdf_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        store(tmp_path, make_pdf_bytes(pages=1, password="secret"))
    assert info.value.code == "encrypted"
    assert all_files(tmp_path) == []


def test_zero_page_pdf_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        store(tmp_path, make_pdf_bytes(pages=0))
    assert info.value.code == "empty"
    assert all_files(tmp_path) == []


def test_too_many_pages_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        store(tmp_path, make_pdf_bytes(pages=MAX_PAGES + 1))
    assert info.value.code == "too_many_pages"
    assert all_files(tmp_path) == []


def test_exactly_max_pages_is_accepted(tmp_path: Path) -> None:
    assert store(tmp_path, make_pdf_bytes(pages=MAX_PAGES)).page_count == MAX_PAGES


def test_probe_timeout_is_reported_as_corrupt_and_cleaned_up(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        store_pdf(
            io.BytesIO(make_pdf_bytes()),
            upload_dir=tmp_path,
            project_id=1,
            filename="a.pdf",
            max_bytes=MAX_BYTES,
            max_pages=MAX_PAGES,
            probe_timeout=0.001,
        )
    assert info.value.code == "corrupt"
    assert all_files(tmp_path) == []


# --- path safety -------------------------------------------------------------

HOSTILE_NAMES = [
    "../../x.pdf",
    "..\\..\\x.pdf",
    "C:\\Windows\\system32\\x.pdf",
    "/etc/passwd",
    "folder/sub/paper.pdf",
    "..",
    ".",
    "",
    "\x00evil.pdf",
    "a" * 1000 + ".pdf",
    "pa\u202epdf.exe",
    "r\u00e9sum\u00e9 \u2014 \u8bba\u6587.pdf",
]


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
def test_hostile_filenames_never_affect_the_stored_path(tmp_path: Path, hostile: str) -> None:
    upload_dir = tmp_path / "uploads"
    stored = store(upload_dir, make_pdf_bytes(), filename=hostile)

    expected_dir = (upload_dir / "7").resolve()
    assert stored.path.parent == expected_dir
    assert stored.path.name == stored.stored_filename
    assert stored.path.is_file()
    # nothing was written anywhere else under tmp_path
    outside = [p for p in all_files(tmp_path) if not p.resolve().is_relative_to(upload_dir)]
    assert outside == []
    assert 0 < len(stored.display_name) <= 255
    assert "/" not in stored.display_name and "\\" not in stored.display_name


def test_sanitize_display_name_cases() -> None:
    assert sanitize_display_name("paper.pdf") == "paper.pdf"
    assert sanitize_display_name("../../x.pdf") == "x.pdf"
    assert sanitize_display_name("C:\\dir\\y.pdf") == "y.pdf"
    assert sanitize_display_name(None) == "document.pdf"
    assert sanitize_display_name("   ") == "document.pdf"
    assert sanitize_display_name("..") == "document.pdf"
    assert sanitize_display_name("a\u202eb.pdf") == "ab.pdf"  # bidi override removed
    assert sanitize_display_name("a\x00b\x07c.pdf") == "abc.pdf"  # control chars removed
    assert len(sanitize_display_name("z" * 1000)) == 255
    assert sanitize_display_name("r\u00e9sum\u00e9.pdf") == "r\u00e9sum\u00e9.pdf"


# --- paths, deletion ----------------------------------------------------------


def test_stored_file_path_rejects_unexpected_names(tmp_path: Path) -> None:
    for bad in ["../x.pdf", "abc.pdf", "A" * 32 + ".pdf", "0" * 32 + ".txt", "", "0" * 32]:
        with pytest.raises(ValueError):
            stored_file_path(tmp_path, 1, bad)


def test_delete_stored_file_removes_only_that_file(tmp_path: Path) -> None:
    keep = store(tmp_path, make_pdf_bytes(pages=1))
    drop = store(tmp_path, make_pdf_bytes(pages=2))
    assert delete_stored_file(tmp_path, 7, drop.stored_filename) is True
    assert not drop.path.exists()
    assert keep.path.exists()
    assert delete_stored_file(tmp_path, 7, drop.stored_filename) is False  # already gone


def test_delete_project_files_removes_only_that_project(tmp_path: Path) -> None:
    mine = store(tmp_path, make_pdf_bytes(), project_id=1)
    other = store(tmp_path, make_pdf_bytes(), project_id=2)
    assert delete_project_files(tmp_path, 1) is True
    assert not mine.path.exists()
    assert other.path.exists()
    assert delete_project_files(tmp_path, 1) is True  # missing folder is fine


def test_no_directories_are_created_until_something_is_stored(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    assert not upload_dir.exists()
    store(upload_dir, make_pdf_bytes())
    assert upload_dir.exists()
