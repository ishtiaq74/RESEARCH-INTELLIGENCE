# HANDOFF

Last updated by: Antigravity (T1.2a done)

## Current state
- T0-CONTINUITY: **done**.
- T1.1 Backend skeleton: **done**.
- T1.1b Linting: **done** — ruff 0.17.1, mypy 2.4.0, all pinned.
- T1.2a Frontend skeleton: **done** — Next.js 16.4.2, App Router, TypeScript strict, ESLint.
  - All versions pinned in package.json.
  - `npm run lint` → passed, `npx tsc --noEmit` → passed, `npm run build` → compiled successfully.

## In progress
- **T1.2b**: Home page that fetches /health and displays status, version, app_name with loading/error states.

## Next step
- Complete T1.2b → T1.2c → T1.2d, then wait for owner to approve T1.3.

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
