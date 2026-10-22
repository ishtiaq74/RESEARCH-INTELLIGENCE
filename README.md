# Research Intelligence

A multi-document academic research workspace. Upload academic PDFs, ask questions across papers, and get evidence-grounded answers with citations you can inspect back to the exact page and passage. The primary differentiator is verifiable academic evidence, not merely conversational answers about PDFs.

> **Status: scaffold only.** No product features exist yet. The backend serves a `/health` endpoint; the frontend displays its response. Authentication, PDF upload, ingestion, and Q&A are not implemented.

---

## Requirements

| Tool | Minimum | How verified |
|------|---------|-------------|
| Python | **3.12** | `pyproject.toml` sets `requires-python = ">=3.12"`; verified with Python 3.12.10 |
| Node.js | **20** | `frontend/README.md` states 20+; verified with Node.js 24.15.0 (`node --version`) |
| Git | any recent | — |

**Docker is not needed.** The database is SQLite (a local file).

> **Note on folder location:** Do **not** clone this repo inside a OneDrive-synced folder (e.g. `Desktop`, `Documents`, `OneDrive`). SQLite WAL mode and `node_modules` do not work reliably under cloud sync. Use a plain local path such as `C:\dev\research-intelligence`.

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
uvicorn app.main:app --reload
# Running at http://localhost:8000
# Health check: http://localhost:8000/health
```

> **If you see "uvicorn is not recognized":** the virtual environment is not active.  
> Run `.venv\Scripts\Activate.ps1` first. Your prompt should show `(.venv)` before you proceed.

### Alembic: which folder to run from

Alembic commands **must be run from the `backend\` folder** with `-c alembic.ini` (or `-c backend\alembic.ini` from the repo root):

```powershell
# From backend\ (recommended):
alembic -c alembic.ini upgrade head
alembic -c alembic.ini current

# From the repo root (also works):
backend\.venv\Scripts\alembic -c backend\alembic.ini upgrade head
```

**Verified:** both forms print `INFO [alembic.runtime.migration] Context impl SQLiteImpl.` without error.

---

## Frontend setup

Run all frontend commands from the `frontend\` folder.

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

pytest tests\ -v                      # 22 tests, all should pass
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

### "uvicorn is not recognized" (or any backend command not found)
The virtual environment is not active. Run `.venv\Scripts\Activate.ps1` from `backend\`. Confirm your prompt shows `(.venv)`.

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
