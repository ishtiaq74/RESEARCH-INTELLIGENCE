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
D-015 — No email verification in the MVP. Reason: avoids requiring an external transactional email provider or SMTP setup during initial development, keeping onboarding frictionless and zero-cost. Alt: verification link sent via email on signup. Status: Approved.
D-016 — No Google sign-in in T2, email + password only. Reason: avoids third-party OAuth registration, API console credentials, and redirect URI complexity during local development. Alt: Google OAuth2 / social login. Status: Approved.
D-017 — SQLite behind the repositories layer. Reason: keeps database access and data models encapsulated behind repository interfaces, ensuring SQLite fulfills zero-cost local development while enabling a clean swap to PostgreSQL if multi-user production hosting requires it. Alt: direct ORM or SQL queries spread across route handlers and service layers. Status: Approved.
D-018 — Password reset uses a one-time expiring token and an EmailSender interface; in dev the link is logged to the console; real email delivery is deferred until a free provider is chosen. Reason: enables the password reset flow to be implemented and tested end-to-end locally without requiring email infrastructure or paid services. Alt: omit password reset entirely in MVP, or hardcode an external SMTP service. Status: Proposed - awaiting owner approval.
D-019 — Session cookie Secure flag comes from config (`SESSION_COOKIE_SECURE`), defaulting to True in production and False in local development/tests. Reason: Host header is client-controlled and must never decide security flags ("localhost.evil.com" matches startswith("localhost")); explicit configuration provides a reliable toggle. Status: Approved.
D-020 — Identical 404 for missing and not-owned projects. Reason: Returning 403 Forbidden on a project owned by another user reveals that the project exists, allowing project enumeration probing. Returning 404 with identical message and structure hides resource existence entirely. Alt: return 403 Forbidden for cross-user attempts. Status: Approved.
D-021 — Project name rules: strip leading and trailing whitespace, require 1 to 100 characters. Reason: Prevents empty, whitespace-only, or excessively long names in UI and database. Enforced in both request schemas (ConfigDict(str_strip_whitespace=True) + Field(min_length=1, max_length=100)) and service validation. Whitespace-only returns 422. Alt: unstripped names or longer limits. Status: Approved.
D-022 — Pagination limits: GET /projects default limit 50, maximum limit 100 (Query le=100, limit > 100 returns 422), offset >= 0. Response remains a plain JSON list. Reason: Prevents unbounded DB queries and memory spikes while keeping client deserialization simple. Alt: unpaginated list or wrapped envelope {items, total}. Status: Approved.
D-023 — Project list ordered by id ascending. Reason: Provides deterministic pagination and chronological insertion ordering for project listing. Alt: order by updated_at descending. Status: Approved.

## Known limitations
- Duplicate-email 409 reveals registered emails: Returning 409 Conflict on registration with an existing email allows account enumeration via signup probing.
- Rate limiter is in-process, keyed by email only, unbounded dictionary, can be used to lock out a victim: An attacker submitting repeated wrong passwords for a known user email will trigger a lockout for that victim; the in-memory dictionary grows with unique email attempts until server restart.
- Deployment requires frontend and API on the same site for SameSite=Lax cookies: Browsers do not attach SameSite=Lax cookies on cross-site asynchronous requests (fetch/XHR), requiring the frontend and backend to share the same registrable domain (e.g. `app.example.com` and `api.example.com`).
- Project DELETE removes only the database row: DELETE /projects/{id} deletes the row in SQLite. Downstream artifacts (stored PDF files in T3, chunks and vector embeddings in T4) will not be cascade-deleted by the database; T3 and T4 must explicitly implement file and vector cleanup when a project is deleted.
- Integer IDs are guessable: Sequential integer primary keys can be traversed/enumerated. This is acceptable because all queries strictly scope by owner_id in the data layer and return an identical 404 for missing and non-owned projects, preventing data leaks or existence probing. Alt: UUIDs.
