# TASKS

Status values: todo | in-progress | done | blocked

## T0-CONTINUITY — status: done
Goal: continuity docs and GitHub remote exist.
- [x] T0.1 Repo initialized, docs committed and pushed to GitHub
- [x] T0.2 Fresh session passes the resume test (states project state correctly from docs alone)
Acceptance: files visible on GitHub; new session answers resume prompt correctly.

## T1-SCAFFOLD — status: done
Goal: empty skeleton, no product features.
- [x] T1.1 Backend skeleton: FastAPI, GET /health, env-based config, layered folders, one passing test
- [x] T1.2 Frontend skeleton: Next.js + TypeScript page that calls /health
  - [x] T1.2a–d: skeleton, home page, CORS config, frontend env
  - [x] T1.2e-1: Testable app factory — create_app(cfg) optional param; test_cors.py rewritten
  - [x] T1.2e-2: Enforce no wildcard — field_validator on cors_origins; wildcard/empty raise at startup
  - [x] T1.2e-3: Narrow CORS — allow_credentials=False, methods=[GET,OPTIONS], headers=[Content-Type,Authorization]
  - [x] T1.2e-4: next.config.ts explained — cacheComponents+partialPrefetching are documented Next.js 15+ features added by create-next-app; comments added; lint/tsc/build pass
- [x] T1.3 SQLite database + Alembic (replaces Docker/Postgres T1.3)
  - [x] T1.3-0 Correct the notes (docs only, no code)
  - [x] T1.3a Database module (SQLAlchemy 2.x, engine, session, data/ folder, tests)
  - [x] T1.3b FTS5 check (virtual table MATCH query test)
  - [x] T1.3c Alembic (empty initial migration, upgrade/downgrade test)
- [x] T1.3d Review findings on T1.3
  - [x] T1.3d-1 Settings path test (no set_main_option; env-var only; real-db safety check in try/finally)
  - [x] T1.3d-2 No side effects on import (data/ not created until first connection)
  - [x] T1.3d-3 Document batch-mode + foreign-keys migration risk in HANDOFF and DECISIONS_LOG
  - [x] T1.3d-4 Check docs commit history and set accurate next step
- [x] T1.4 README with exact run steps; verify from a fresh clone
  - [x] T1.4a Root README.md (project desc, requirements, backend/frontend setup, checks, troubleshooting, layout)
  - [x] T1.4b Alembic usage note (verified from backend/ and repo root; both succeed)
  - [x] T1.4c Fresh-clone verification (follow README only; fix if wrong)
  - [x] T1.4d Stop before merging (report and wait for architect review)
  - [x] T1.4e Record minor known items in HANDOFF.md Known problems
  - [x] T1.4f README fixes (Node requirements provenance, Alembic table with pasted output, uvicorn command, troubleshooting)
Acceptance: fresh clone runs from README; /health OK and shown in UI; migration applies cleanly; no secrets in repo; lint and type-check pass.
- [x] T1.5 Dependency audit & final polish
  - [x] T1.5a README Node fix (Node.js minimum 20.9 matching Next.js engines.node)
  - [x] T1.5b Frontend audit (npm audit report, runtime vs dev, safe fix analysis)
  - [x] T1.5c Backend audit (pip-audit report in temporary venv)
  - [x] T1.5d ESLint assessment (eslint 9.x status and Next.js compatibility)
  - [x] T1.5e Write docs/DEPENDENCY_AUDIT.md and stop before merge
  - [x] T1.5f Correct DEPENDENCY_AUDIT.md (raw severities, owner upgrade note, braces *, prod claims, watch list)

## T2 Auth and projects — status: done
Goal: users can register, sign in and own private projects. No other user can see them.
- [x] T2.1 Backend auth (email + password, server-side sessions in SQLite, Alembic migration, CORS adjusted for cookies)
  - [x] T2.1a Users and sessions schema + Alembic migration with foreign keys and SQLite batch mode
  - [x] T2.1b Repositories layer (user_repository and session_repository storing SHA-256 token hashes)
  - [x] T2.1c Service layer (Argon2id password hashing, in-process rate limiter, session management)
  - [x] T2.1d Auth router (/register, /login, /logout, /me) with httpOnly, SameSite=Lax cookie
  - [x] T2.1e Security fixes (SESSION_COOKIE_SECURE config, dummy hash module constant, session creation split, duplicate email race handling, 128 max password length, expired session deletion on lookup, rate limiter expiry reset)
- [x] T2.2 Projects backend (projects table, owner scoping in the repositories layer, CRUD, cross-user isolation tests)
  - [x] T2.2a Projects schema & Alembic migration (projects table, owner_id FK with CASCADE, created_at, updated_at, index on owner_id)
  - [x] T2.2b Dynamic migration tests (compute head with ScriptDirectory, inspect down_revision for projects migration parent)
  - [x] T2.2c Repositories layer (project_repository scoping every query by owner_id and id, with pagination limit/offset)
  - [x] T2.2d Service layer (project_service with ProjectError, ProjectNotFoundError, name validation, and strict owner propagation)
  - [x] T2.2e Projects router & schemas (ConfigDict str_strip_whitespace=True, 1-100 char name limit, pagination limit/offset, real datetime fields in ProjectResponse with model_validate, no type: ignore)
  - [x] T2.2f CORS cleanup (removed expose_headers=["set-cookie"] per WHATWG Fetch spec, added PATCH preflight)
  - [x] T2.2g Comprehensive test suite (99 passing backend tests: CRUD happy paths, unauthenticated 401s, 422 on whitespace-only/length violations, 404 on missing and not-owned, identical response bodies for cross-user and missing ids, pagination slicing and 100 cap)
- [x] T2.3 Frontend: sign-in, sign-up, project list and create pages
  - [x] T2.3a Tests setup (Vitest 4.1.12, React Testing Library 16.3.3, jsdom, @vitejs/plugin-react, trivial test passing, npm audit verified with 0 vulnerabilities)
  - [x] T2.3b API client module (lib/api.ts with typed auth and project functions, credentials: "include", centralized error mapping, 15 unit tests passing)
  - [x] T2.3c Auth pages (app/register/page.tsx, app/login/page.tsx, auth.module.css, client-side password length 8-128 hint, disabled submit while submitting, aria-live errors, GET /auth/me client-side UX guard)
  - [x] T2.3d Projects page (app/projects/page.tsx, projects.module.css, loading/empty/error/list states, create form with trimmed 1-100 char validation, inline rename, delete confirmation step, sign-out button, 401 redirect)
  - [x] T2.3e Component test suite (tests/auth-pages.test.tsx, tests/projects-page.test.tsx with mocked API client, 36 frontend tests passing)
  - [x] T2.3f Docs update (TASKS.md, HANDOFF.md with local setup instructions, SESSION_COOKIE_SECURE=false, localhost vs 127.0.0.1 explanation)
  - [x] T2.3g Bug fix: clear page and auth state on sign-out and submit (reset isSigningOut in finally, wipe user/project data and reset phase to loading on sign-out to prevent Cache Components / React Activity state leakage across user sessions, clear password state after submit and unmount, 40 tests passing)
- [x] T2.4 Security and isolation review & hardening batch
  - [x] T2.4a Security review and vulnerability analysis (Security review completed by the architect; integer bounds and the JSON 500 / CORS behaviour are covered by automated tests (test_huge_integer_bounds_returns_422, test_unhandled_error_returns_json_500_with_cors_headers))
  - [x] T2.4b Step 1: Integer bounds (project_id Path bounded to 1 <= id <= 2**63 - 1, offset capped at 1_000_000, returns 422)
  - [x] T2.4c Step 2: Origin check middleware (OriginCheckMiddleware blocks disallowed origins on POST, PUT, PATCH, DELETE with 403)
  - [x] T2.4d Step 3: Unhandled errors (ErrorHandlingMiddleware catches exceptions, logs traceback, returns JSON 500 with CORS headers)
  - [x] T2.4e Step 4: Rate limiter (15-minute failure window, 10,000-key table pruning, _now helper for testing, accurate docstring)
  - [x] T2.4f Step 5: Expired sessions (delete_expired_sessions called on successful login, old expired rows pruned)
  - [x] T2.4g Step 6: Cache-Control (CacheControlMiddleware sets Cache-Control: no-store on /auth and /projects)
  - [x] T2.4h Step 7: Config validation (CORS origins validated for http/https scheme, no trailing slash, no path/query; startup warning on insecure cookie with non-localhost)
  - [x] T2.4i Step 8: Docs accuracy (CSRF section in dependencies.py rewritten with correct SameSite=Lax, CORS, and origin explanations)
  - [x] T2.4j Step 9: Frontend Content-Type (apiRequest sets application/json only for string bodies, never for FormData; 42 frontend tests passing)
  - [x] T2.4k Step 10: Docs update (DECISIONS_LOG.md Known limitations updated, TASKS.md updated; HANDOFF.md moves to T2.5)
- [x] T2.5 HANDOFF.md state-at-end-of-T2 section added and README setup notes checked
Acceptance: user A cannot read, list, change or delete user B's projects by any endpoint; passwords never stored or logged in plaintext; all checks and tests pass.

## T3 Secure PDF upload and storage — todo
## T4 Ingestion (page-level extraction, chunking, quality checks) — todo
## T5 Retrieval and evaluation set — todo
## T6 Grounded answers, citation validation, abstention — todo
## T7 Citation inspector — todo
## T8 Paper comparison — todo
## T9 Literature review drafting — todo

(Detailed sub-steps for T3 onward will be added by the architect before each task starts.)
