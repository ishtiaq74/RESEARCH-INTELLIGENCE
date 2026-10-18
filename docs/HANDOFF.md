# HANDOFF

Last updated by: Antigravity (T1.2b/c/d done)

## Current state
- T0-CONTINUITY: **done**.
- T1.1 Backend skeleton: **done**.
- T1.1b Linting: **done** — ruff 0.17.1, mypy 2.4.0, all pinned.
- T1.2a Frontend skeleton: **done** — Next.js 16.4.2, App Router, TypeScript strict, ESLint, all pinned.
- T1.2b Home page: **done** — fetches `{NEXT_PUBLIC_API_BASE_URL}/health`, shows loading/ok/error states. Boilerplate SVGs removed, dark-mode CSS removed, README replaced.
- T1.2c Backend CORS: **done** — `CORS_ORIGINS` setting (comma-separated, default `http://localhost:3000`, no wildcard), wired via CORSMiddleware. Test confirms allowed origin gets header, disallowed does not.
- T1.2d Frontend env: **done** — `frontend/.env.example` with `NEXT_PUBLIC_API_BASE_URL`.

## In progress
- Nothing. Waiting for owner to confirm live test observations and approve T1.3.

## Next step
- **T1.3**: Docker Compose with Postgres + pgvector; Alembic with one empty migration. (Do not start until owner says so.)

## Known problems / open questions
- LLM provider not chosen (D-010).
- Owner's computer specs (RAM / GPU) unknown, affects whether a local LLM is practical.
- Email verification / Google sign-in and hosting jurisdiction undecided (not needed until later).
- `httpx` deprecation warning from `starlette.testclient` (harmless now; fix when upgrading starlette).

## How to run

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\uvicorn app.main:app --reload   # http://localhost:8000/health
.venv\Scripts\pytest tests\ -v
.venv\Scripts\ruff check app/ tests/
.venv\Scripts\mypy app/ tests/
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
