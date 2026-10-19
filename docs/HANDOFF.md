# HANDOFF

Last updated by: Antigravity (T1.2e-1/2/3/4 done)

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

## In progress
- Nothing. T1.2e complete. Waiting for owner to approve T1.3.

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
