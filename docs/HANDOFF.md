# HANDOFF

Last updated by: Antigravity (T1.5f done)

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
- T1.3d-1 Settings path tested: **done** — new test `test_alembic_migration_via_settings_env_var` asserts `sqlalchemy.url` is absent from alembic.ini, sets DB only via `DATABASE_URL` env var, runs full lifecycle, and asserts real `data/app.db` was not created or modified. Test proven meaningful: temporarily breaking `get_url()` causes it to fail with `OperationalError: no such table: alembic_version`.
- T1.3d-2 No side effects on import: **done** — `session.py` uses custom SQLite creator so `data/` folder creation is deferred to first connection; import of `session.py` / `main.py` has no filesystem side effects; verified via isolated subprocess test `test_import_side_effects.py`.
- T1.3d-1 follow-up: **done** — wrapped migration lifecycle and assertions in `test_alembic_migration_via_settings_env_var` in a `try/finally` block so the real-db safety check and engine disposal always run even if migration commands fail.
- T1.3d-3 Document batch-mode migration risk: **done** — recorded SQLite batch-mode + foreign keys migration risk note in HANDOFF.md and DECISIONS_LOG.md (D-014).
- T1.3d-4 Docs verification & clean handoff: **done** — verified via `git log --stat -8 --oneline -- docs` that all 8 recent commits updated both `HANDOFF.md` and `TASKS.md`.
- T1.4a Root README: **done** — wrote `README.md` at repo root covering project description, requirements, backend/frontend setup (Windows PowerShell), health-check verification, checks commands, troubleshooting, project layout.
- T1.4b Alembic usage note: **done** — verified `alembic -c alembic.ini current` from `backend\` and `backend\.venv\Scripts\alembic -c backend\alembic.ini current` from repo root; both succeed. Documented in README.
- T1.4c Fresh-clone verification: **done** — cloned origin/t1-scaffold into a temporary directory outside repo and OneDrive ($env:TEMP\ri-fresh-clone-test); followed README step-by-step with no extra knowledge; venv creation, activation, pip install, alembic upgrade head, pytest (22 passed), ruff, mypy, npm ci, npm run lint, npm run type-check, and npm run build all verified passing; temporary clone deleted.
- T1.4e Minor known items recorded: **done** — documented SQLite URL prefix edge case, custom creator URL options bypass, and unused ensure_data_dir in Known problems.
- T1.4f README fixes: **done** — refined README.md with Node requirement provenance and tested version, OneDrive sync warning clarification, uvicorn default command with --port 8000 and --reload note, Alembic table with real outputs showing migration revision 7c75c84bb53a from backend and root, clarified frontend path from repo root, removed hardcoded test count, and added execution policy and npm audit troubleshooting entries.
- T1.5a README Node fix: **done** — updated Node.js minimum to 20.9 in README.md Requirements table to match Next.js engines.node ">=20.9.0".
- T1.5b Frontend audit: **done** — ran npm audit, saved raw output to docs/audit-raw/npm-audit.txt; identified 5 high severity findings (all in a single dev-only chain rooted in braces <=3.0.3); verified dev-only via npm ls --omit=dev; not plausibly exploitable in our codebase (used for file path globs during ESLint, not on untrusted input).
- T1.5c Backend audit: **done** — created isolated temporary venv outside repo, installed pip-audit, audited installed packages and pinned pyproject.toml dependencies; saved outputs to docs/audit-raw/pip-audit-installed.txt (0 app runtime vulnerabilities; 1 dev transitive in certifi 2026.10.18 fixed in 2026.10.19; 6 unique tooling advisories in virtualenv pip 25.0.1) and docs/audit-raw/pip-audit-pinned.txt (no known vulnerabilities found); deleted temporary venv.
- T1.5d ESLint assessment: **done** — verified npm view eslint dist-tags (maintenance: 9.39.5, latest: 10.13.0) and eslint-config-next@16.4.2 peerDependencies (eslint: >=9.0.0); saved to docs/audit-raw/eslint-versions.txt; peer dependency allows ESLint 10; lowest-risk upgrade path is deferring ESLint 10 to T2 to avoid major version churn during scaffold.
- T1.5e Write docs/DEPENDENCY_AUDIT.md: **done** — created docs/DEPENDENCY_AUDIT.md summarizing frontend and backend audit findings, severity, scope, usage analysis, recommended actions, and fix risks.
- T1.5f Correct DEPENDENCY_AUDIT.md: **done** — updated docs/DEPENDENCY_AUDIT.md to state raw severities ("not stated by pip-audit"), recorded owner local venv upgrade of pip (26.2.2) and certifi (2026.10.19) with 22 passing tests, updated braces to "braces *" without "<= 3.0.3" and "fixed version", saved npm-audit-prod.txt (0 vulnerabilities), clarified backend production scan scope (transitive inclusion unverified), and added Watch list section.

## In progress
None (T1 complete, stopped before merge per instructions).

## Next step
Owner reviews DEPENDENCY_AUDIT.md; then merge t1-5-audit and start T2 (auth and projects); architect writes the T2 task.

## Known problems / open questions
- When the first migration alters tables that have foreign keys, SQLite batch mode rebuilds the table. With PRAGMA foreign_keys=ON this can fail or cascade. Revisit in env.py at T2: disable foreign key enforcement during migrations and run PRAGMA foreign_key_check afterward. Unverified until a real migration exists.
- session.py: is_sqlite uses startswith("sqlite") but folder creation uses startswith("sqlite:///"); a URL like sqlite+pysqlite:///path would break. Unused today.
- The custom creator bypasses SQLAlchemy's SQLite connect handling, so URL options (timeout, uri) are ignored. Add a busy timeout if "database is locked" appears.
- ensure_data_dir() in config.py is probably unused by app code (only a test). Remove or reuse it at T2.
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
