# HANDOFF

Last updated by: Antigravity (T1.3c done)

## Current state
- T0-CONTINUITY: **done**.
- T1.1 Backend skeleton: **done**.
- T1.1b Linting: **done** — ruff 0.17.1, mypy 2.4.0, all pinned.
- T1.2a Frontend skeleton: **done** — Next.js 16.4.2, App Router, TypeScript strict, ESLint, all pinned.
- T1.2b Home page: **done** — fetches `{NEXT_PUBLIC_API_BASE_URL}/health`, shows loading/ok/error states. Boilerplate SVGs removed, dark-mode CSS removed, README replaced.
- T1.2c Backend CORS: **done** — `CORS_ORIGINS` setting (comma-separated, default `http://localhost:3000`, no wildcard), wired via CORSMiddleware. Test confirms allowed origin gets header, disallowed does not.
- T1.2d Frontend env: **done** — `frontend/.env.example` with `NEXT_PUBLIC_API_BASE_URL`.
- T1.2e-1 Testable app factory: **done** — `create_app()` accepts `cfg: Settings | None`; `app = create_app()` at module level preserved. `test_cors.py` rewritten to use `create_app(Settings(cors_origins=...))` directly; hand-built `_make_client` removed.
- T1.2e-2 No-wildcard enforcement: **done** — `Settings` now has a `field_validator` that raises `ValueError` at startup if `cors_origins` is empty or contains `*`. Tests: wildcard raises, wildcard-in-list raises, empty raises.
- T1.2e-3 Narrow CORS: **done** — `allow_credentials=False`, `allow_methods=["GET", "OPTIONS"]`, `allow_headers=["Content-Type", "Authorization"]`. Comment in code: "T2 will revisit allow_methods and allow_headers when auth is designed."
- T1.2e-4 next.config.ts explained: **done** — `cacheComponents` and `partialPrefetching` are both documented Next.js 15+/16+ features. Both were added by create-next-app during T1.2a scaffolding. Comments added in next.config.ts. Frontend checks: lint passed, tsc --noEmit passed, npm run build passed.
- T1.3-0 Correct notes: **done** — replaced Docker/Postgres plan in TASKS.md, HANDOFF.md, and DECISIONS_LOG.md (D-004) with SQLite + Alembic as approved by owner on 2026-10-19.
- T1.3a Database module: **done** — SQLAlchemy 2.1.6 pinned, synchronous engine in app/db/session.py with SQLite pragmas (foreign_keys=ON, journal_mode=WAL), session dependency, BACKEND_DIR/data/app.db SQLite URL default, anchored .env, data/ auto-creation and gitignored, 8 new passing tests.
- T1.3b FTS5 check: **done** — verified SQLite FTS5 extension with virtual table and MATCH query test (Python 3.12.10, SQLite 3.49.1).
- T1.3c Alembic: **done** — Alembic 1.20.1 pinned, backend/alembic.ini without hardcoded URL, env.py reading URL dynamically from app Settings with SQLite batch mode (render_as_batch=True), one empty initial migration, migration lifecycle test passing (upgrade head -> upgrade head -> downgrade base -> upgrade head).

## In progress
- T1.3 Final verification (Step 5).

## Next step
- **T1.4**: README with exact run steps; verify from a fresh clone.

## Known problems / open questions
- LLM provider not chosen (D-010).
- Owner's laptop: 8 GB RAM, no Docker (SQLite chosen; local LLM likely impractical or must be very small quantized CPU model; provider interface deferred to D-010).
- Email verification / Google sign-in and hosting jurisdiction undecided (not needed until later).
- `httpx` deprecation warning from `starlette.testclient` (harmless now; fix when upgrading starlette).

## How to run

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\alembic -c alembic.ini upgrade head
.venv\Scripts\uvicorn app.main:app --reload   # http://localhost:8000/health
.venv\Scripts\pytest tests\ -v
.venv\Scripts\ruff check app/ tests/ alembic/
.venv\Scripts\mypy app/ tests/ alembic/
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local          # set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                          # http://localhost:3000
npm run lint
npm run type-check
npm run build
```

## Update rule
After every sub-step, update this file: Current state, In progress, Next step, Known problems.
