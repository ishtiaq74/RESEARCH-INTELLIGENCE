"""Tests for no filesystem side effects on module import."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_import_does_not_create_data_dir(tmp_path: Path) -> None:
    """Importing app.db.session must not create any folder or file.

    Uses a subprocess to guarantee a completely clean import state.
    The data folder is created only on first connection, not at import time.
    """
    # A directory that definitely does not exist yet
    absent_db_dir = tmp_path / "must_not_be_created_on_import"
    assert not absent_db_dir.exists()

    db_url = f"sqlite:///{absent_db_dir.as_posix()}/app.db"

    # Script that:
    # 1. Sets DATABASE_URL to point into the absent directory
    # 2. Imports app.db.session (and therefore app.main)
    # 3. Asserts the directory does NOT exist yet
    # 4. Creates a connection and asserts it NOW exists
    # 5. Prints "OK" if all assertions pass
    script = f"""
import os, sys
os.environ["DATABASE_URL"] = {db_url!r}

# Add backend to sys.path
sys.path.insert(0, r"{Path(__file__).parent.parent}")

from pathlib import Path
absent_dir = Path({absent_db_dir.as_posix()!r})

# --- import must not create the directory ---
import app.db.session  # noqa: F401

if absent_dir.exists():
    print("FAIL: directory was created at import time", flush=True)
    sys.exit(1)

# --- first connection must create the directory ---
from sqlalchemy import text
from app.db.session import create_db_engine
engine = create_db_engine({db_url!r})
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
engine.dispose()

if not absent_dir.exists():
    print("FAIL: directory was NOT created after first connection", flush=True)
    sys.exit(2)

print("OK", flush=True)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"Subprocess failed (exit {result.returncode}).\n"
        f"stdout: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout, (
        f"Expected 'OK' in subprocess stdout.\n"
        f"stdout: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )
    # Confirm the directory was created (by the subprocess's connection)
    assert absent_db_dir.exists(), (
        f"After subprocess ran, {absent_db_dir} should exist but does not."
    )
