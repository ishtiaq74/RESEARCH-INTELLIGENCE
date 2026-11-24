"""Tests for T3.1b document upload API endpoints.

Coverage:
  - Upload (POST /projects/{id}/documents):
      - Success 201, correct DocumentRead fields returned
      - Unauthenticated 401
      - Project not found / other user's project → 404 (identical body)
      - 413 by Content-Length header exceeding limit
      - 413 by streamed body exceeding limit (no Content-Length)
      - 415 for non-PDF bytes
      - 422 for corrupt PDF
      - 422 for encrypted PDF
      - 422 for empty PDF (0 pages)
      - 422 for PDF with too many pages
      - 409 for duplicate document content (same SHA-256)
      - 422 when project document limit reached
      - Disallowed Origin → 403 before any processing
      - stored_filename, sha256 are NOT present in response JSON
      - No leftover .tmp files after rejected upload
      - File cleaned up on delete

  - List (GET /projects/{id}/documents):
      - Returns caller's documents (200)
      - Unauthenticated → 401
      - Other user's project → 404
      - Pagination bounds (limit 0, limit 101, offset -1, offset > 1_000_000) → 422

  - Get (GET /projects/{id}/documents/{doc_id}):
      - 200 on own document
      - 401 unauthenticated
      - 404 wrong project
      - 404 wrong document id
      - Cross-user isolation: user B cannot get A's document → 404

  - Delete (DELETE /projects/{id}/documents/{doc_id}):
      - 204 on success
      - 401 unauthenticated
      - 404 wrong project
      - 404 wrong document id
      - File removed from disk after DELETE
      - Cross-user isolation: user B cannot delete A's document → 404

  - UploadSizeGuard middleware:
      - 413 by Content-Length header alone (no bytes sent)
      - 413 by streaming body exceeding limit
      - Normal upload passes through size guard (201)
      - GET requests are NOT blocked by size guard
      - 413 response has CORS headers and Cache-Control: no-store

Each test uses a fresh in-memory (file) SQLite database with the full migration
applied, plus a tmp upload directory via Settings override, identical to
test_projects.py and test_auth.py patterns.
"""
from __future__ import annotations

import io
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from alembic import command
from app.config import BACKEND_DIR, Settings
from app.db.session import create_db_engine, create_session_factory, get_db
from app.main import create_app
from app.services.auth_service import reset_rate_limiter

# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------


def _make_minimal_pdf(*, pages: int = 1, encrypted: bool = False) -> bytes:
    """Return a minimal valid (or encrypted) PDF as bytes.

    For pages=0 we return a PDF stub that the probe will reject as empty.
    For encrypted=True we insert a /Encrypt dictionary so pypdf raises.
    This avoids depending on pypdf in the test suite for fixture generation.
    """
    if encrypted:
        # A PDF with /Encrypt in the trailer — pypdf raises PdfReadError
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
            b"xref\n0 3\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"trailer\n<< /Size 3 /Root 1 0 R /Encrypt 99 0 R >>\n"
            b"startxref\n107\n%%EOF\n"
        )
    if pages == 0:
        # Zero-page PDF: valid structure but /Count 0
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
            b"xref\n0 3\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"trailer\n<< /Size 3 /Root 1 0 R >>\n"
            b"startxref\n107\n%%EOF\n"
        )
    # Build a minimal PDF with the given number of pages using pypdf
    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=72, height=72)
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()
    except ImportError:
        # Fallback: hand-craft a single-page PDF (pages arg ignored beyond 1)
        page = (
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] >>\nendobj\n"
        )
        xref_offset = len(b"%PDF-1.4\n") + len(page)
        xref = (
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000062 00000 n \n"
            b"0000000119 00000 n \n"
        )
        trailer = f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
        return b"%PDF-1.4\n" + page + xref + trailer


def _not_pdf() -> bytes:
    """Return bytes that are definitely not a PDF."""
    return b"This is plain text, not a PDF."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_rate_limiter() -> Generator[None, None, None]:
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture()
def db_and_client(tmp_path: Path) -> Generator[tuple[Session, TestClient, Settings], None, None]:
    """Yield (db_session, test_client, cfg) backed by a fresh migrated SQLite DB.

    Settings are overridden to:
      - Use a tmp upload_dir so tests don't touch the real data/uploads folder.
      - Set session_cookie_secure=False so TestClient (HTTP) can read cookies.
      - Set a small max_upload_bytes (1 MiB) for size-guard tests.
    """
    db_file = tmp_path / "test_documents.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    factory = create_session_factory(engine)

    cfg = Settings(
        cors_origins="http://localhost:3000",
        session_cookie_secure=False,
        upload_dir=upload_dir,
        max_upload_bytes=1024 * 1024,  # 1 MiB for size-guard tests
        max_pdf_pages=10,
        max_documents_per_project=3,
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(cfg)
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app, raise_server_exceptions=True)

    db = factory()
    try:
        yield db, client, cfg
    finally:
        db.close()
        engine.dispose()


def _register_and_login(client: TestClient, email: str, password: str = "strongpass1") -> None:
    resp = client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text


def _login(client: TestClient, email: str, password: str = "strongpass1") -> None:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text


def _create_project(client: TestClient, name: str = "My Project") -> int:
    resp = client.post("/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


def _upload_pdf(
    client: TestClient, project_id: int, pdf_bytes: bytes, filename: str = "test.pdf"
) -> Any:
    return client.post(
        f"/projects/{project_id}/documents",
        files={"file": (filename, io.BytesIO(pdf_bytes), "application/pdf")},
    )


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


class TestUpload:
    def test_upload_success_201(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """Successful upload returns 201 and a DocumentRead with the right fields."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        pdf = _make_minimal_pdf(pages=1)

        resp = _upload_pdf(client, pid, pdf)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["project_id"] == pid
        assert data["status"] == "uploaded"
        assert isinstance(data["id"], int)
        assert isinstance(data["original_filename"], str)
        assert isinstance(data["size_bytes"], int)
        assert data["size_bytes"] > 0

    def test_upload_no_internal_fields(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """stored_filename, sha256, and path must NOT appear in the response JSON."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = _upload_pdf(client, pid, _make_minimal_pdf(pages=1))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "stored_filename" not in data
        assert "sha256" not in data
        assert "path" not in data

    def test_upload_unauthenticated_401(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        client.cookies.clear()

        resp = _upload_pdf(client, pid, _make_minimal_pdf())
        assert resp.status_code == 401

    def test_upload_wrong_project_404(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")

        resp = _upload_pdf(client, 99999, _make_minimal_pdf())
        assert resp.status_code == 404

    def test_upload_other_user_project_404(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """User B cannot upload into User A's project; 404 body equals nonexistent project."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        # Switch to user B
        client.cookies.clear()
        _register_and_login(client, "b@example.com")

        resp_cross = _upload_pdf(client, pid, _make_minimal_pdf())
        resp_missing = _upload_pdf(client, 99999, _make_minimal_pdf())
        assert resp_cross.status_code == 404
        assert resp_missing.status_code == 404
        assert resp_cross.json() == resp_missing.json()

    def test_upload_415_not_pdf(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = _upload_pdf(client, pid, _not_pdf())
        assert resp.status_code == 415

    def test_upload_422_corrupt_pdf(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = _upload_pdf(client, pid, b"%PDF-1.4\ncorrupt-not-valid-pdf-structure")
        assert resp.status_code == 422

    def test_upload_422_encrypted_pdf(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = _upload_pdf(client, pid, _make_minimal_pdf(encrypted=True))
        assert resp.status_code == 422

    def test_upload_422_empty_pdf(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = _upload_pdf(client, pid, _make_minimal_pdf(pages=0))
        assert resp.status_code == 422

    def test_upload_422_too_many_pages(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """PDF with more pages than max_pdf_pages (set to 10 in fixture) → 422."""
        _, client, cfg = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        pdf = _make_minimal_pdf(pages=cfg.max_pdf_pages + 1)
        resp = _upload_pdf(client, pid, pdf)
        assert resp.status_code == 422

    def test_upload_409_duplicate(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        pdf = _make_minimal_pdf(pages=1)

        r1 = _upload_pdf(client, pid, pdf)
        assert r1.status_code == 201
        r2 = _upload_pdf(client, pid, pdf)
        assert r2.status_code == 409

    def test_upload_422_project_limit(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """Uploading beyond max_documents_per_project (3 in fixture) → 422."""
        _, client, cfg = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        for i in range(cfg.max_documents_per_project):
            pdf = _make_minimal_pdf(pages=i + 1)
            resp = _upload_pdf(client, pid, pdf, filename=f"doc{i}.pdf")
            assert resp.status_code == 201, f"Upload {i} failed: {resp.text}"

        # One more → 422
        extra = _make_minimal_pdf(pages=cfg.max_documents_per_project + 1)
        resp = _upload_pdf(client, pid, extra, filename="extra.pdf")
        assert resp.status_code == 422

    def test_upload_disallowed_origin_403(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """POST with a disallowed Origin header → 403 from OriginCheckMiddleware."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = client.post(
            f"/projects/{pid}/documents",
            files={"file": ("t.pdf", io.BytesIO(_make_minimal_pdf()), "application/pdf")},
            headers={"Origin": "http://evil.example.com"},
        )
        assert resp.status_code == 403

    def test_upload_no_leftover_tmp_after_rejected_upload(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """Rejected uploads (non-PDF) must leave no .tmp partial files on disk."""
        _, client, cfg = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = _upload_pdf(client, pid, _not_pdf())
        assert resp.status_code == 415

        tmp_dir = cfg.upload_dir / ".tmp"
        if tmp_dir.exists():
            remaining = list(tmp_dir.iterdir())
            assert remaining == [], f"Leftover tmp files: {remaining}"


# ---------------------------------------------------------------------------
# Size guard tests
# ---------------------------------------------------------------------------


class TestSizeGuard:
    def test_413_by_content_length_header(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """Content-Length header exceeding limit → 413 without reading any body bytes."""
        _, client, cfg = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        over_limit = cfg.max_upload_bytes + 1024 * 1024  # 1 MiB over

        # Send Content-Length header manually with a small body; size guard checks header first
        resp = client.post(
            f"/projects/{pid}/documents",
            content=b"x" * 10,  # tiny body, but header claims it's huge
            headers={
                "Content-Length": str(over_limit),
                "Content-Type": "multipart/form-data; boundary=testboundary",
            },
        )
        assert resp.status_code == 413

    def test_413_by_streamed_body(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """Streaming body exceeding limit without Content-Length → 413."""
        _, client, cfg = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        # Build a chunked multipart stream via a generator so httpx omits Content-Length.
        boundary = "testboundary"
        total_body_bytes = cfg.max_upload_bytes + 32 * 1024  # well over max + overhead
        chunk = b"X" * 8192

        def stream_chunks() -> Generator[bytes, None, None]:
            yield (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode()
            sent = 0
            while sent < total_body_bytes:
                yield chunk
                sent += len(chunk)
            yield f"\r\n--{boundary}--\r\n".encode()

        resp = client.post(
            f"/projects/{pid}/documents",
            content=stream_chunks(),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        assert resp.status_code == 413

    def test_raw_asgi_streamed_413_stops_reading_and_sends_once(self) -> None:
        """Direct ASGI test: streamed 413 sends one response and stops reading chunks."""
        import asyncio
        from collections.abc import MutableMapping

        from starlette.requests import Request
        from starlette.responses import JSONResponse

        from app.middleware import UploadSizeGuard

        async def multipart_consumer(scope: Any, receive: Any, send: Any) -> None:
            req = Request(scope, receive)
            await req.form()
            await JSONResponse({"ok": True})(scope, receive, send)

        guard = UploadSizeGuard(multipart_consumer, max_bytes=1024)
        chunks_pulled = 0

        async def fake_receive() -> MutableMapping[str, Any]:
            nonlocal chunks_pulled
            chunks_pulled += 1
            if chunks_pulled == 1:
                header = (
                    b"--b\r\n"
                    b'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n\r\n'
                )
                return {"type": "http.request", "body": header + b"A" * 2048, "more_body": True}
            if chunks_pulled <= 10:
                return {"type": "http.request", "body": b"B" * 4096, "more_body": True}
            return {"type": "http.request", "body": b"\r\n--b--\r\n", "more_body": False}

        sent_messages: list[MutableMapping[str, Any]] = []

        async def fake_send(msg: MutableMapping[str, Any]) -> None:
            sent_messages.append(msg)

        scope: dict[str, Any] = {
            "type": "http",
            "method": "POST",
            "path": "/projects/1/documents",
            "headers": [(b"content-type", b"multipart/form-data; boundary=b")],
        }
        asyncio.run(guard(scope, fake_receive, fake_send))

        starts = [m for m in sent_messages if m["type"] == "http.response.start"]
        assert len(starts) == 1
        assert starts[0]["status"] == 413
        # Must abort early without pulling all 10 chunks
        assert chunks_pulled <= 2

    def test_normal_upload_passes_size_guard(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """A valid small PDF passes through the size guard successfully."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = _upload_pdf(client, pid, _make_minimal_pdf(pages=1))
        assert resp.status_code == 201

    def test_get_not_blocked_by_size_guard(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """GET /projects/{id}/documents is NOT blocked by the upload size guard."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = client.get(f"/projects/{pid}/documents")
        assert resp.status_code == 200

    def test_413_has_cors_and_cache_control_headers(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """413 from size guard carries CORS headers and Cache-Control: no-store."""
        _, client, cfg = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        over_limit = cfg.max_upload_bytes + 1024 * 1024

        resp = client.post(
            f"/projects/{pid}/documents",
            content=b"x" * 10,
            headers={
                "Content-Length": str(over_limit),
                "Content-Type": "multipart/form-data; boundary=testboundary",
                "Origin": "http://localhost:3000",
            },
        )
        assert resp.status_code == 413
        assert resp.headers.get("cache-control") == "no-store"
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---------------------------------------------------------------------------
# List tests
# ---------------------------------------------------------------------------


class TestListDocuments:
    def test_list_returns_200_empty(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp = client.get(f"/projects/{pid}/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_uploaded_documents(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        for i in range(2):
            resp = _upload_pdf(client, pid, _make_minimal_pdf(pages=i + 1), filename=f"doc{i}.pdf")
            assert resp.status_code == 201

        resp = client.get(f"/projects/{pid}/documents")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_unauthenticated_401(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        client.cookies.clear()

        assert client.get(f"/projects/{pid}/documents").status_code == 401

    def test_list_other_user_project_404(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        client.cookies.clear()
        _register_and_login(client, "b@example.com")

        assert client.get(f"/projects/{pid}/documents").status_code == 404

    def test_list_pagination_invalid_limit_0(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        assert client.get(f"/projects/{pid}/documents?limit=0").status_code == 422

    def test_list_pagination_invalid_limit_101(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        assert client.get(f"/projects/{pid}/documents?limit=101").status_code == 422

    def test_list_pagination_invalid_offset_negative(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        assert client.get(f"/projects/{pid}/documents?offset=-1").status_code == 422

    def test_list_pagination_invalid_offset_too_large(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        assert client.get(f"/projects/{pid}/documents?offset=1000001").status_code == 422


# ---------------------------------------------------------------------------
# Get tests
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_get_200(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        doc_id = _upload_pdf(client, pid, _make_minimal_pdf()).json()["id"]

        resp = client.get(f"/projects/{pid}/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id

    def test_get_unauthenticated_401(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        doc_id = _upload_pdf(client, pid, _make_minimal_pdf()).json()["id"]
        client.cookies.clear()

        assert client.get(f"/projects/{pid}/documents/{doc_id}").status_code == 401

    def test_get_wrong_project_404(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")

        assert client.get("/projects/99999/documents/1").status_code == 404

    def test_get_wrong_document_404(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        assert client.get(f"/projects/{pid}/documents/99999").status_code == 404

    def test_get_cross_user_isolation_404_equal_body(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """User B gets 404 for A's document; body matches nonexistent project."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        doc_id = _upload_pdf(client, pid, _make_minimal_pdf()).json()["id"]

        client.cookies.clear()
        _register_and_login(client, "b@example.com")

        resp_cross = client.get(f"/projects/{pid}/documents/{doc_id}")
        resp_cross_missing_doc = client.get(f"/projects/{pid}/documents/99999")
        resp_missing_proj = client.get("/projects/99999/documents/99999")
        assert resp_cross.status_code == 404
        assert resp_cross_missing_doc.status_code == 404
        assert resp_missing_proj.status_code == 404
        # Identical JSON body prevents leaking whether A's project or doc_id exists
        assert resp_cross.json() == resp_missing_proj.json()
        assert resp_cross_missing_doc.json() == resp_missing_proj.json()

    def test_path_integer_bounds_return_422(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """Out-of-range project_id or document_id returns 422 instead of 500."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        too_big = 2**63

        assert client.get("/projects/0/documents").status_code == 422
        assert client.get(f"/projects/{too_big}/documents").status_code == 422
        assert client.get(f"/projects/{pid}/documents/0").status_code == 422
        assert client.get(f"/projects/{pid}/documents/{too_big}").status_code == 422
        assert client.delete(f"/projects/{pid}/documents/{too_big}").status_code == 422


# ---------------------------------------------------------------------------
# Delete tests
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    def test_delete_204(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, cfg = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        pdf = _make_minimal_pdf(pages=1)
        doc = _upload_pdf(client, pid, pdf).json()

        resp = client.delete(f"/projects/{pid}/documents/{doc['id']}")
        assert resp.status_code == 204

    def test_delete_removes_file_from_disk(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """After DELETE the stored file must no longer exist on disk."""
        _, client, cfg = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        resp_up = _upload_pdf(client, pid, _make_minimal_pdf())
        assert resp_up.status_code == 201

        project_dir = cfg.upload_dir / str(pid)
        files_before = list(project_dir.rglob("*.pdf"))
        assert len(files_before) == 1

        doc_id = resp_up.json()["id"]
        assert client.delete(f"/projects/{pid}/documents/{doc_id}").status_code == 204

        files_after = list(project_dir.rglob("*.pdf"))
        assert files_after == []

    def test_delete_unauthenticated_401(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        doc_id = _upload_pdf(client, pid, _make_minimal_pdf()).json()["id"]
        client.cookies.clear()

        assert client.delete(f"/projects/{pid}/documents/{doc_id}").status_code == 401

    def test_delete_wrong_project_404(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")

        assert client.delete("/projects/99999/documents/1").status_code == 404

    def test_delete_wrong_document_404(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)

        assert client.delete(f"/projects/{pid}/documents/99999").status_code == 404

    def test_delete_cross_user_isolation_404(
        self, db_and_client: tuple[Session, TestClient, Settings]
    ) -> None:
        """User B cannot delete A's document; 404 body matches nonexistent project."""
        _, client, _ = db_and_client
        _register_and_login(client, "a@example.com")
        pid = _create_project(client)
        doc_id = _upload_pdf(client, pid, _make_minimal_pdf()).json()["id"]

        client.cookies.clear()
        _register_and_login(client, "b@example.com")

        resp_cross = client.delete(f"/projects/{pid}/documents/{doc_id}")
        resp_cross_missing_doc = client.delete(f"/projects/{pid}/documents/99999")
        resp_missing_proj = client.delete("/projects/99999/documents/99999")
        assert resp_cross.status_code == 404
        assert resp_cross_missing_doc.status_code == 404
        assert resp_missing_proj.status_code == 404
        assert resp_cross.json() == resp_missing_proj.json()
        assert resp_cross_missing_doc.json() == resp_missing_proj.json()
