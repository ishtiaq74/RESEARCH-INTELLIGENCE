# DECISIONS LOG

Format: ID — decision — reason — alternatives — status.

D-001 — Monorepo: /frontend, /backend, /docs. Simple for a solo owner and one builder agent. Status: proposed.
D-002 — Frontend: Next.js + TypeScript. Mature, good PDF viewer libraries. Alt: Vite + React. Status: proposed.
D-003 — Backend: Python + FastAPI. Best PDF/AI tooling in Python. Alt: TypeScript backend. Status: proposed.
D-004 — SQLite, approved by owner 2026-10-19. Reasons: 8 GB RAM laptop, no Docker, MVP scale of at most 20 papers per project, SQLite FTS5 covers keyword search, zero cost. All database access stays behind repositories/ using SQLAlchemy, so Postgres can be swapped in later if multi-user hosting needs it.
D-005 — Auth: open-source library for email + password (e.g. FastAPI-Users), not hand-written. Status: proposed; confirm at T2.
D-006 — File storage: local folder behind a storage interface. Free; swappable later. Status: proposed.
D-007 — PDF parsing: PyMuPDF behind a parser interface. Gives page-level text with positions. NOTE: AGPL license; acceptable for a local portfolio build, must be revisited before any public launch. Status: proposed.
D-008 — Background jobs: a `jobs` table plus a worker loop. No Redis/Celery for MVP. Status: proposed.
D-009 — Embeddings: small open-source model on CPU behind an interface. Free; slower. Model choice deferred to T5 and decided by evaluation. Status: proposed.
D-010 — LLM: provider interface; free-tier API and/or local model. Provider NOT yet chosen; owner must check current free-tier limits and data-use terms. Status: open.
D-011 — Scanned PDFs rejected in MVP (no OCR). Status: accepted by owner.
D-012 — Zero-cost rule: no paid services. Status: accepted by owner.
D-013 — Continuity: repo docs are the project's memory; commit, push, and update HANDOFF.md after every sub-step. Status: accepted.
D-014 — SQLite batch-mode migration risk: When the first migration alters tables that have foreign keys, SQLite batch mode rebuilds the table. With PRAGMA foreign_keys=ON this can fail or cascade. Revisit in env.py at T2: disable foreign key enforcement during migrations and run PRAGMA foreign_key_check afterward. Unverified until a real migration exists. Status: noted; action deferred to T2.
