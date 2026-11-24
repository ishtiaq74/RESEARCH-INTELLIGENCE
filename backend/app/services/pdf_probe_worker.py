"""Worker script: inspect ONE PDF and print a single JSON line.

This file is run as a separate Python process by app/services/pdf_probe.py, never
imported by the API. It only imports the standard library and pypdf, so starting it is
cheap and it does not load the rest of the application.

WHY A SEPARATE PROCESS:
  PDF parsers process untrusted, attacker-controlled bytes. A malicious or broken file can
  make a parser loop for a very long time, use a lot of memory or crash the interpreter.
  If that happened inside the API process, the whole API would hang or die. In a child
  process the parent can enforce a timeout and simply kill it.

Output (one JSON object on stdout):
  {"status": "ok", "page_count": N}
  {"status": "encrypted"}
  {"status": "corrupt"}

The worker never tries to decrypt a file: an encrypted PDF is reported as encrypted and
rejected by the caller. page_count is the number the PDF itself declares in its page tree;
the real text extraction in T4 re-checks pages one by one.
"""

from __future__ import annotations

import json
import sys

from pypdf import PdfReader


def _inspect(path: str) -> dict[str, object]:
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            return {"status": "encrypted"}
        return {"status": "ok", "page_count": len(reader.pages)}
    except Exception:  # any parser failure (including RecursionError) means "corrupt"
        return {"status": "corrupt"}


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "corrupt"}))
        return 2
    print(json.dumps(_inspect(sys.argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
