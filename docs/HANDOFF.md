# HANDOFF

Last updated by: Antigravity (T1.1 done)

## Current state
- T0-CONTINUITY: **done**.
- T1.1 Backend skeleton: **done**.
  - `backend/` created: FastAPI app factory, `GET /health`, pydantic-settings config, layered folders (routers / services / repositories / models).
  - 2 tests pass: `test_health_returns_200`, `test_health_response_body`.
  - Test output: `2 passed, 0 failed in 5.07s` (Python 3.12, pytest 9.1.1).

## In progress
- Nothing — T1.1 just committed; about to start T1.2.

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
