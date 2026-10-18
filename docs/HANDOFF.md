# HANDOFF

Last updated by: Antigravity (T1.1b done)

## Current state
- T0-CONTINUITY: **done**.
- T1.1 Backend skeleton: **done**.
- T1.1b Linting: **done** — ruff 0.17.1 and mypy 2.4.0 added, all versions pinned, both pass clean.
  - `ruff check app/ tests/` → All checks passed!
  - `mypy app/ tests/` → Success: no issues found in 10 source files
  - `pytest` → 2 passed in 0.47s

## In progress
- **T1.2a**: Creating frontend/ with Next.js App Router + TypeScript.

## Next step
- **T1.2 Frontend skeleton**: Next.js + TypeScript page that calls `GET /health` and shows the result.

## Known problems / open questions
- LLM provider not chosen (D-010).
- Owner's computer specs (RAM / GPU) unknown, affects whether a local LLM is practical.
- Email verification / Google sign-in and hosting jurisdiction undecided (not needed until later).
- `httpx` deprecation warning from `starlette.testclient` (harmless now; fix when upgrading starlette).

## How to run
```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\uvicorn app.main:app --reload   # http://localhost:8000/health
.venv\Scripts\pytest tests\ -v
```

## Update rule
After every sub-step, update this file: Current state, In progress, Next step, Known problems.
