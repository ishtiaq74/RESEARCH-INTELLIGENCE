# Research Intelligence

A multi-document academic research workspace. Upload academic PDFs, ask questions across papers, and get evidence-grounded answers with citations you can inspect back to the exact page and passage. The primary differentiator is verifiable academic evidence, not merely conversational answers about PDFs.

> **Status: scaffold only.** No product features exist yet. The backend serves a `/health` endpoint; the frontend displays its response. Authentication, PDF upload, ingestion, and Q&A are not implemented.

---

## Requirements

| Tool | Minimum | How verified |
|------|---------|-------------|
| Python | **3.12** | `pyproject.toml` sets `requires-python = ">=3.12"`; verified with Python 3.12.10 |
| Node.js | **20.9** | Tested with 24.15.0 (`node --version`); 20.x minimum comes from `frontend/README.md` and is untested. Next.js 16.4.2 specifies `engines.node: ">=20.9.0"` in `frontend/node_modules/next/package.json`. |
| Git | any recent | — |

**Docker is not needed.** The database is SQLite (a local file).

> **Note on folder location:** Do **not** clone this repo inside a OneDrive-synced folder (e.g. `Desktop`, `Documents`, `OneDrive`). Sync can cause problems with node_modules and SQLite files. Use a plain local path such as `C:\dev\research-intelligence`.

> **macOS/Linux:** The commands below are Windows PowerShell. Equivalent bash commands are listed where they differ, but they are **unverified** — only PowerShell was tested.

---

## Backend setup (Windows PowerShell)

Run all backend commands from the `backend\` folder unless stated otherwise.

```powershell
cd backend

# 1. Create the virtual environment
python -m venv .venv

# 2. ACTIVATE it  (your prompt will change to show (.venv))
.venv\Scripts\Activate.ps1

# macOS/Linux equivalent (unverified):
# source .venv/bin/activate

# 3. Install the package and all dependencies
pip install -e ".[dev]"

# 4. (Optional) Copy the env template
#    The backend works without a .env file; defaults are safe for local dev.
Copy-Item .env.example .env

# 5. Apply database migrations  — creates backend\data\app.db
alembic -c alembic.ini upgrade head

# 6. Start the backend
uvicorn app.main:app --port 8000
# Note: add --reload for development auto-reload (e.g. uvicorn app.main:app --port 8000 --reload)
# Running at http://localhost:8000
# Health check: http://localhost:8000/health
```

> **If you see "uvicorn is not recognized":** the virtual environment is not active.  
> Run `.venv\Scripts\Activate.ps1` first. Your prompt should show `(.venv)` before you proceed.

### Alembic: which folder to run from

| Folder | Commands |
|--------|----------|
| `backend\` (recommended) | `alembic upgrade head`<br>`alembic current` |
| Repo root | `backend\.venv\Scripts\alembic -c backend\alembic.ini <command>` |

**Output verified on temporary database (`7c75c84bb53a`):**

From `backend\`:
```text
> alembic upgrade head
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 7c75c84bb53a, empty initial migration

> alembic current
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
7c75c84bb53a (head)
```

From repo root:
```text
> backend\.venv\Scripts\alembic -c backend\alembic.ini upgrade head
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 7c75c84bb53a, empty initial migration

> backend\.venv\Scripts\alembic -c backend\alembic.ini current
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
7c75c84bb53a (head)
```

---

## Frontend setup

Run all frontend commands from the `frontend\` folder. (From repo root: `cd frontend`; or if in `backend\`: `cd ..\frontend`).

```powershell
cd frontend

# 1. Install exact pinned dependencies (do NOT use npm install — it may update lockfile)
npm ci

# 2. (Optional) Set the backend URL
#    The frontend defaults to http://localhost:8000 if no .env.local is present.
#    Only needed if you change the backend port.
#    Create frontend\.env.local and add:  NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# 3. Start the dev server
npm run dev
# Running at http://localhost:3000
```

---

## Verifying it works

1. With the backend running (`uvicorn`) and the frontend running (`npm run dev`):
   - Open **http://localhost:3000**
   - You should see a health card showing `status: ok`, the app name, and the version.

2. **Stop the backend** (Ctrl+C in its terminal).
   - Reload http://localhost:3000
   - The card should change to an error: `"Could not reach the backend. Is it running on http://localhost:8000?"`

---

## Running the checks

### Backend

```powershell
cd backend
# (virtual environment must be active)

pytest tests\ -v                      # all should pass
ruff check app/ tests/ alembic/       # linter — should print "All checks passed!"
mypy app/ tests/ alembic/             # type checker — should print "Success: no issues found"
```

### Frontend

```powershell
cd frontend

npm run lint        # ESLint
npm run type-check  # tsc --noEmit
npm run build       # production build (optional for local dev)
```

---

## Troubleshooting

### "Activate.ps1 cannot be loaded because running scripts is disabled"
If `Activate.ps1` fails with "running scripts is disabled", run:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
This is run once and affects only the current user.

### "uvicorn is not recognized" (or any backend command not found)
The virtual environment is not active. Run `.venv\Scripts\Activate.ps1` from `backend\`. Confirm your prompt shows `(.venv)`.

### "npm audit" warnings after "npm ci"
npm audit warnings after `npm ci` are expected; do **NOT** run `npm audit fix --force`.

### "Port 8000 is already in use"
Find what is using the port before stopping it:
```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object -Property LocalAddress,LocalPort,OwningProcess
Get-Process -Id <OwningProcess>
```
Check what the process is before stopping it. Stop it only if it is safe to do so.

### Frontend moved to port 3001 (CORS will block it)
Next.js picks port 3001 when 3000 is already taken. The backend's CORS allow-list defaults to `http://localhost:3000` only. Two options:
1. **Free port 3000** so Next.js uses it (recommended).
2. Set `CORS_ORIGINS=http://localhost:3000,http://localhost:3001` in `backend\.env`, then restart uvicorn.

### Alembic "can't locate revision" or similar
Make sure you run `alembic` from `backend\` with `-c alembic.ini`. Running from the repo root without `-c backend\alembic.ini` will fail.

---

## Project layout

```
research-intelligence/
├── backend/                # Python/FastAPI backend
│   ├── app/                # Application source
│   │   ├── config.py       # Settings (pydantic-settings, reads .env)
│   │   ├── main.py         # FastAPI app factory
│   │   └── db/
│   │       └── session.py  # SQLAlchemy engine & session
│   ├── alembic/            # Alembic migrations
│   ├── alembic.ini         # Alembic config (no hardcoded URL)
│   ├── tests/              # pytest tests
│   ├── data/               # SQLite database lives here (gitignored)
│   ├── .env.example        # Copy to .env for local overrides
│   └── pyproject.toml      # Dependencies and tool config
├── frontend/               # Next.js 16 / TypeScript frontend
│   ├── app/                # App Router pages and components
│   └── package.json
└── docs/                   # Project docs — read these first
    ├── AGENT_RULES.md      # Rules for every coding session
    ├── HANDOFF.md          # Current state and next steps
    ├── TASKS.md            # Task list with status
    ├── PROJECT_BRIEF.md    # What the project is
    └── DECISIONS_LOG.md    # Architecture decisions
```

See `docs/` for full project documentation.
