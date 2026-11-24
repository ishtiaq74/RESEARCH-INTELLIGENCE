"""PDF probe: ask "how many pages, and is it encrypted?" without trusting the file.

The actual parsing happens in a child process (see pdf_probe_worker.py) so that a hostile
or pathological PDF can be stopped with a timeout instead of hanging the API.

The child is started with `-I` (isolated mode): it ignores PYTHON* environment variables,
the user site-packages and the current directory, so it only runs the worker script.

KNOWN LIMITATION: Windows has no simple per-process memory limit, so this protects against
hangs and crashes (timeout, process isolation) but not against a file that tries to use a
lot of memory. The 20 MiB upload limit keeps that bounded in practice.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_WORKER = Path(__file__).with_name("pdf_probe_worker.py")

DEFAULT_TIMEOUT_SECONDS: float = 10.0


class PdfProbeError(Exception):
    """The file could not be analysed. `reason` is 'corrupt' or 'timeout'."""

    def __init__(self, reason: Literal["corrupt", "timeout"], message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class PdfProbeResult:
    """Outcome of a probe. page_count is None when the file is encrypted."""

    is_encrypted: bool
    page_count: int | None


def probe_pdf(path: Path, timeout_s: float = DEFAULT_TIMEOUT_SECONDS) -> PdfProbeResult:
    """Return page count and encryption status for the PDF at `path`.

    Raises PdfProbeError('timeout') if the worker runs longer than timeout_s, and
    PdfProbeError('corrupt') if the worker crashes, prints something unexpected or
    reports that the file cannot be parsed.
    """
    try:
        completed = subprocess.run(  # fixed argument list, no shell
            [sys.executable, "-I", str(_WORKER), str(path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills the child before raising TimeoutExpired.
        raise PdfProbeError("timeout", "PDF analysis took too long.") from exc

    if completed.returncode != 0:
        raise PdfProbeError("corrupt", "PDF analysis failed.")

    try:
        data = json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise PdfProbeError("corrupt", "PDF analysis returned no result.") from exc

    status = data.get("status") if isinstance(data, dict) else None
    if status == "encrypted":
        return PdfProbeResult(is_encrypted=True, page_count=None)
    if status == "ok":
        count = data.get("page_count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            return PdfProbeResult(is_encrypted=False, page_count=count)
    raise PdfProbeError("corrupt", "The PDF could not be read.")
