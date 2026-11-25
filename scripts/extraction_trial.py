"""
extraction_trial.py — T4.1b throwaway trial script.

Purpose: Compare core PyMuPDF (no pymupdf4llm or layout) and pypdf for
         page-level text extraction on PDFs in C:/dev/trial-pdfs/.
         Outputs JSON results to C:/dev/trial-pdfs/out/results.json.

NOT meant to be imported by app code.
Run with the temporary trial venv:
    C:/dev/t4-trial-venv/Scripts/python scripts/extraction_trial.py

Design WHY:
- Run both libraries on the exact same PDF files and compare per-page text,
  empty-page counts, elapsed wall time, and Python heap peak memory.
- Import core `pymupdf` only (`page.get_text("text")`), avoiding `pymupdf4llm`
  and `pymupdf.layout`, and record matching loaded module names from `sys.modules`
  to verify whether extra layout/LLM modules are loaded for plain per-page text.
- Record both `empty_pages` (len == 0) and `whitespace_only_pages`
  (len(text.strip()) == 0) because whitespace-only extractions from scanned or
  blank pages are functionally empty for RAG chunking.
- Write all output under C:/dev/trial-pdfs/out/ (outside the repo) so no PDF
  text or trial artifacts are ever committed to Git.
"""

from __future__ import annotations

import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

PDF_DIR = Path(r"C:\dev\trial-pdfs")
OUT_DIR = Path(r"C:\dev\trial-pdfs\out")


def _tracked_modules(prefixes: tuple[str, ...]) -> list[str]:
    """Return sorted loaded sys.modules keys matching any given substring."""
    return sorted(
        name for name in sys.modules if any(part in name.lower() for part in prefixes)
    )


def extract_pymupdf(pdf_path: Path) -> dict[str, Any]:
    """Extract per-page plain text using core PyMuPDF only."""
    import pymupdf

    tracemalloc.start()
    t0 = time.perf_counter()

    pages: list[dict[str, Any]] = []
    with pymupdf.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text")
            pages.append(
                {
                    "page_index": i,
                    "char_count": len(text),
                    "stripped_char_count": len(text.strip()),
                    "text": text,
                }
            )

    elapsed = time.perf_counter() - t0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    chars_per_page = [p["char_count"] for p in pages]
    loaded_modules = _tracked_modules(
        ("pymupdf", "fitz", "onnx", "numpy", "networkx", "layout", "4llm")
    )

    return {
        "library": "PyMuPDF",
        "version": pymupdf.__version__,
        "mupdf_version": pymupdf.version[1],
        "pdf": pdf_path.name,
        "file_size_bytes": pdf_path.stat().st_size,
        "page_count": len(pages),
        "empty_pages": sum(1 for c in chars_per_page if c == 0),
        "whitespace_only_pages": sum(
            1 for p in pages if p["stripped_char_count"] == 0
        ),
        "total_chars": sum(chars_per_page),
        "chars_per_page": chars_per_page,
        "elapsed_seconds": round(elapsed, 4),
        "peak_memory_bytes": peak_bytes,
        "loaded_related_modules": loaded_modules,
        "pages": pages,
    }


def extract_pypdf(pdf_path: Path) -> dict[str, Any]:
    """Extract per-page plain text using pypdf."""
    import pypdf
    from pypdf import PdfReader

    tracemalloc.start()
    t0 = time.perf_counter()

    reader = PdfReader(str(pdf_path))
    pages: list[dict[str, Any]] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            text = f"[EXTRACTION_ERROR: {exc}]"
        pages.append(
            {
                "page_index": i,
                "char_count": len(text),
                "stripped_char_count": len(text.strip()),
                "text": text,
            }
        )

    elapsed = time.perf_counter() - t0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    chars_per_page = [p["char_count"] for p in pages]

    return {
        "library": "pypdf",
        "version": pypdf.__version__,
        "pdf": pdf_path.name,
        "file_size_bytes": pdf_path.stat().st_size,
        "page_count": len(pages),
        "empty_pages": sum(1 for c in chars_per_page if c == 0),
        "whitespace_only_pages": sum(
            1 for p in pages if p["stripped_char_count"] == 0
        ),
        "total_chars": sum(chars_per_page),
        "chars_per_page": chars_per_page,
        "elapsed_seconds": round(elapsed, 4),
        "peak_memory_bytes": peak_bytes,
        "loaded_related_modules": _tracked_modules(("pypdf",)),
        "pages": pages,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"ERROR: No PDF files found in {PDF_DIR}")
        sys.exit(1)

    print(f"Found {len(pdf_files)} PDF(s): {[p.name for p in pdf_files]}")
    results: list[dict[str, Any]] = []

    for pdf_path in pdf_files:
        print(f"\n=== {pdf_path.name} ({pdf_path.stat().st_size} bytes) ===")
        for fn in (extract_pymupdf, extract_pypdf):
            res = fn(pdf_path)
            print(
                f"  {res['library']} {res['version']}: "
                f"pages={res['page_count']}, "
                f"total_chars={res['total_chars']}, "
                f"empty={res['empty_pages']}, "
                f"ws_only={res['whitespace_only_pages']}, "
                f"time={res['elapsed_seconds']}s, "
                f"py_peak={res['peak_memory_bytes'] // 1024} KiB"
            )
            results.append(res)

    out_path = OUT_DIR / "results.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
