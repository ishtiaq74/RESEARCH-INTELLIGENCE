"""Safe storage of uploaded PDFs on disk.

This module knows nothing about HTTP, users or the database. It takes a byte stream and
either returns a StoredFile (the PDF now lives at <upload_dir>/<project_id>/<uuid>.pdf)
or raises StorageError and leaves NOTHING behind on disk.

WHY THE CLIENT'S FILENAME IS NEVER A PATH:
  A filename like "../../app/main.py" or "C:\\Windows\\x" is attacker-controlled. If it were
  joined into a path, an upload could overwrite files outside the upload folder (path
  traversal). Here the stored name is always a random UUID we generate, and the client's
  name is kept only as a cleaned-up label for display.

WHY WRITE TO A TEMP FILE FIRST:
  We must check size, the %PDF- header and the PDF structure before the file becomes
  "real". Writing to <upload_dir>/.tmp first and then os.replace() into the final place
  means a half-written or rejected file can never appear as a stored document.

WHY STOP READING AS SOON AS THE FILE IS TOO BIG:
  The size limit is enforced while streaming, so an oversized stream is cut off early.
  (The HTTP layer must also limit the request body, because the web framework may buffer
  the upload before this code runs. That is handled separately in the upload endpoint.)
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from app.services.pdf_probe import DEFAULT_TIMEOUT_SECONDS, PdfProbeError, probe_pdf

_CHUNK_BYTES = 1024 * 1024  # 1 MiB
_PDF_MAGIC = b"%PDF-"
_TMP_DIRNAME = ".tmp"
_MAX_DISPLAY_NAME_CHARS = 255
_FALLBACK_DISPLAY_NAME = "document.pdf"
_STORED_NAME_RE = re.compile(r"^[0-9a-f]{32}\.pdf$")

StorageErrorCode = Literal[
    "too_large",
    "not_pdf",
    "corrupt",
    "encrypted",
    "empty",
    "too_many_pages",
]


class StorageError(Exception):
    """The upload was rejected. `code` says why; nothing was stored."""

    def __init__(self, code: StorageErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StoredFile:
    """Metadata of a PDF that was stored successfully."""

    stored_filename: str
    path: Path
    sha256: str
    size_bytes: int
    page_count: int
    display_name: str


def sanitize_display_name(name: str | None) -> str:
    """Return a safe, short label for a client-supplied filename.

    Removes any folder part (both / and \\ separators), control and invisible formatting
    characters (this includes the bidirectional-override characters used to disguise file
    names), surrounding spaces and dots, and limits the length. The result is only ever
    shown to the user; it is never used to build a path.
    """
    if not name:
        return _FALLBACK_DISPLAY_NAME
    cleaned = unicodedata.normalize("NFC", name)
    cleaned = re.split(r"[\\/]", cleaned)[-1]
    cleaned = "".join(ch for ch in cleaned if unicodedata.category(ch) not in {"Cc", "Cf", "Cs"})
    cleaned = cleaned.strip(" .")[:_MAX_DISPLAY_NAME_CHARS].strip(" .")
    return cleaned or _FALLBACK_DISPLAY_NAME


def _inside(root: Path, candidate: Path) -> bool:
    return candidate.resolve().is_relative_to(root.resolve())


def store_pdf(
    stream: BinaryIO,
    *,
    upload_dir: Path,
    project_id: int,
    filename: str | None,
    max_bytes: int,
    max_pages: int,
    probe_timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> StoredFile:
    """Validate the PDF in `stream` and store it under upload_dir/<project_id>/<uuid>.pdf.

    Checks, in order: size (while streaming), %PDF- header, PDF structure (via the
    subprocess probe), encryption, page count. Raises StorageError on any failure and
    removes every temporary file it created.
    """
    root = upload_dir.resolve()
    tmp_dir = root / _TMP_DIRNAME
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}.part"

    try:
        digest = hashlib.sha256()
        size = 0
        header = b""
        with open(tmp_path, "xb") as out:
            while True:
                chunk = stream.read(_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise StorageError("too_large", "The file is too large.")
                if len(header) < len(_PDF_MAGIC):
                    header = (header + chunk)[: len(_PDF_MAGIC)]
                    if len(header) >= len(_PDF_MAGIC) and header != _PDF_MAGIC:
                        raise StorageError("not_pdf", "The file is not a PDF.")
                digest.update(chunk)
                out.write(chunk)

        if header != _PDF_MAGIC:
            raise StorageError("not_pdf", "The file is not a PDF.")

        try:
            result = probe_pdf(tmp_path, timeout_s=probe_timeout)
        except PdfProbeError as exc:
            raise StorageError("corrupt", "The PDF could not be read.") from exc

        if result.is_encrypted:
            raise StorageError("encrypted", "Encrypted PDFs are not supported.")
        if not result.page_count:
            raise StorageError("empty", "The PDF has no pages.")
        if result.page_count > max_pages:
            raise StorageError("too_many_pages", f"The PDF has more than {max_pages} pages.")

        stored_filename = f"{uuid.uuid4().hex}.pdf"
        project_dir = root / str(project_id)
        final_path = project_dir / stored_filename
        if not _inside(root, final_path):
            raise RuntimeError("Refusing to store outside the upload directory.")
        project_dir.mkdir(parents=True, exist_ok=True)
        os.replace(tmp_path, final_path)

        return StoredFile(
            stored_filename=stored_filename,
            path=final_path,
            sha256=digest.hexdigest(),
            size_bytes=size,
            page_count=result.page_count,
            display_name=sanitize_display_name(filename),
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def stored_file_path(upload_dir: Path, project_id: int, stored_filename: str) -> Path:
    """Return the path of a stored file, refusing anything that is not one of ours.

    stored_filename must be exactly 32 lowercase hex characters plus ".pdf" (what
    store_pdf generates), so a corrupted database value can never escape the folder.
    """
    if not _STORED_NAME_RE.fullmatch(stored_filename):
        raise ValueError("Invalid stored filename.")
    path = upload_dir.resolve() / str(project_id) / stored_filename
    if not _inside(upload_dir, path):
        raise ValueError("Path escapes the upload directory.")
    return path


def delete_stored_file(upload_dir: Path, project_id: int, stored_filename: str) -> bool:
    """Delete one stored PDF. Returns True if a file was removed, False if it was missing."""
    path = stored_file_path(upload_dir, project_id, stored_filename)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def delete_project_files(upload_dir: Path, project_id: int) -> bool:
    """Remove the whole folder of a project (used when the project is deleted).

    Returns True if the folder is gone afterwards. Returns False if something could not
    be removed (for example a file locked on Windows); the caller should log a warning.
    """
    root = upload_dir.resolve()
    target = root / str(project_id)
    if not _inside(root, target) or target == root:
        raise ValueError("Invalid project folder.")
    shutil.rmtree(target, ignore_errors=True)
    return not target.exists()
