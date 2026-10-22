# TASKS

Status values: todo | in-progress | done | blocked

## T0-CONTINUITY — status: done
Goal: continuity docs and GitHub remote exist.
- [x] T0.1 Repo initialized, docs committed and pushed to GitHub
- [x] T0.2 Fresh session passes the resume test (states project state correctly from docs alone)
Acceptance: files visible on GitHub; new session answers resume prompt correctly.

## T1-SCAFFOLD — status: in-progress
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
- [ ] T1.3d Review findings on T1.3
  - [x] T1.3d-1 Settings path test (no set_main_option; env-var only; real-db safety check in try/finally)
  - [x] T1.3d-2 No side effects on import (data/ not created until first connection)
  - [ ] T1.3d-3 Document batch-mode + foreign-keys migration risk in HANDOFF and DECISIONS_LOG
- [ ] T1.4 README with exact run steps; verify from a fresh clone
Acceptance: fresh clone runs from README; /health OK and shown in UI; migration applies cleanly; no secrets in repo; lint and type-check pass.

## T2 Auth and projects — todo
## T3 Secure PDF upload and storage — todo
## T4 Ingestion (page-level extraction, chunking, quality checks) — todo
## T5 Retrieval and evaluation set — todo
## T6 Grounded answers, citation validation, abstention — todo
## T7 Citation inspector — todo
## T8 Paper comparison — todo
## T9 Literature review drafting — todo

(Detailed sub-steps for T2 onward will be added by the architect before each task starts.)
