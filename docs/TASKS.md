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
- [ ] T1.2 Frontend skeleton: Next.js + TypeScript page that calls /health
- [ ] T1.3 Docker Compose with Postgres + pgvector; Alembic with one empty migration
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
