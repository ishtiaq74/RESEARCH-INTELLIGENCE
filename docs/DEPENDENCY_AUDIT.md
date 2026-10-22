# Dependency Audit Report

**Date of Audit:** 2026-10-23  
**Audited Branch:** `t1-5-audit`  
**Tools Used:** `npm audit` (frontend), `pip-audit` (backend, executed in an isolated temporary virtualenv outside the repository)

---

## Executive Summary

- **Frontend Production Dependencies:** `npm audit --omit=dev` reports `found 0 vulnerabilities` (saved to `docs/audit-raw/npm-audit-prod.txt`).
- **Backend Production Dependencies:** `pip-audit backend` against `backend/pyproject.toml` reported `No known vulnerabilities found` (saved to `docs/audit-raw/pip-audit-pinned.txt`); whether transitive production dependencies were included by `pip-audit` in this project directory scan is unverified.
- **Frontend Findings (Dev-only):** 5 `high` severity vulnerabilities reported by `npm audit`, all stemming from a single dev-only transitive dependency (`braces *` via `eslint-config-next`). No fixed version exists yet in the npm registry (`latest` is `3.0.3`). `npm audit fix --force` would downgrade Next.js linting to Next 14, which is a breaking change for Next.js 16.
- **Backend Findings (Installed Environment):**
  - Scanning the local virtualenv packages detected `certifi 2026.10.18` (pulled in only via `httpx` for `pytest`) and 6 unique tooling advisories in the virtual environment's internal `pip 25.0.1`.
  - On 2026-10-23, the owner upgraded `pip` to `26.2.2` and `certifi` to `2026.10.19` in the local backend `.venv`, and all 22 backend tests passed afterwards.
- **ESLint Status:** `eslint@9.39.5` is on the `maintenance` dist-tag and prints a deprecation notice. `eslint-config-next@16.4.2` peerDependencies permits `eslint >= 9.0.0` (including ESLint 10), but upgrading to ESLint 10 is a major version change.

---

## Audit Findings Table

| Package | Severity | Layer / Scope | Used by us? | Recommended Action | Risk of Fix |
|---|---|---|---|---|---|
| `braces` (`*`) | High (`GHSA-vfj7-8cjw-p6xm`) | Dev-only (`eslint-config-next` &rarr; `@next/eslint-plugin-next` &rarr; `fast-glob` &rarr; `micromatch` &rarr; `braces`) | No. Stack-exhaustion DoS requires evaluating untrusted deeply-nested brace strings. ESLint only evaluates repository file paths during linting. | **Ignore with reason**. Do not run `npm audit fix --force`. Re-evaluate at T2 if a fixed version is published. | **High** if forced (downgrades `eslint-config-next` to 14.x, breaking Next 16). **Zero risk** to keep as-is. |
| `micromatch`, `fast-glob`, `@next/eslint-plugin-next`, `eslint-config-next` | High (inherited) | Dev-only | No (inherited via `braces`). | **Ignore with reason**. Part of the same ESLint dev toolchain cascade. | **High** if forced downgrade. |
| `certifi` (`2026.10.18`) | not stated by pip-audit (`PYSEC-2026-4320`) | Dev-only transitive (`httpx` &rarr; `httpcore` &rarr; `certifi` for `TestClient`) | No. `TestClient` in `tests/` performs in-process ASGI dispatch; no external TLS traffic to untrusted emSign roots occurs. | **Fixed in the owner's local venv. certifi and pip are not declared in pyproject.toml, so the repo itself is unchanged.** | **Very Low** (patch bump). |
| `pip` (`25.0.1`) | not stated by pip-audit (6 unique advisories: `PYSEC-2026-1795`, `1796`, `2875`, `2876`, `196`, `3721`) | Tooling (virtualenv installer package in `.venv`) | No. We do not download packages from untrusted indexes or run malicious wheel archives; Python 3.12 implements PEP 706. | **Fixed in the owner's local venv. certifi and pip are not declared in pyproject.toml, so the repo itself is unchanged.** | **Very Low** (standard tooling update). |
| `eslint` (`9.39.5`) | Low / Deprecation notice (no CVE) | Dev-only | Yes, for `npm run lint`. | **Fix at T2**. Retain `9.39.5` for scaffold completion; test upgrade to ESLint 10 in a separate branch during T2. | **Medium** (major version jump to ESLint 10; requires verifying plugin and flat-config compatibility). |

---

## Detailed Notes & Evidence

### 1. Frontend: `braces` via `eslint-config-next`
`npm audit` reports:
```text
braces  *
Severity: high
braces vulnerable to stack-exhaustion denial of service through deeply nested patterns - https://github.com/advisories/GHSA-vfj7-8cjw-p6xm
fix available via `npm audit fix --force`
Will install eslint-config-next@14.2.35, which is a breaking change
```
- Direct verification with `npm audit --omit=dev` (saved to `docs/audit-raw/npm-audit-prod.txt`) proves `found 0 vulnerabilities` in production dependencies.
- `npm view braces dist-tags` confirms `latest: '3.0.3'`, meaning no fixed version is currently available in the npm registry.
- Running `npm audit fix --force` must be avoided as it forcefully downgrades `eslint-config-next` to version 14.

### 2. Backend: `certifi` and `pip`
- `pip-audit c:\dev\research-intelligence\backend` against declared dependencies in `pyproject.toml` yields `No known vulnerabilities found` (saved to `docs/audit-raw/pip-audit-pinned.txt`). Whether transitive production dependencies were included by `pip-audit` in this project directory scan is unverified.
- Scanning the local virtualenv packages detected `certifi 2026.10.18`. `pip show certifi` confirms it is required solely by `httpcore` and `httpx` (pinned under `[project.optional-dependencies] dev`). The fixed version is `2026.10.19`.
- The 6 `pip` advisories are restricted to package installation tooling in `.venv` and do not affect runtime execution.
- On 2026-10-23, the owner upgraded `pip` to `26.2.2` and `certifi` to `2026.10.19` in the local backend `.venv`, and all 22 backend tests passed afterwards. Because neither `pip` nor `certifi` are declared in `pyproject.toml`, the repository files remain unchanged.

### 3. ESLint Version Compatibility
- `npm view eslint dist-tags` shows:
  ```json
  {
    "maintenance": "9.39.5",
    "latest": "10.13.0"
  }
  ```
- `npm view eslint-config-next@16.4.2 peerDependencies` specifies:
  ```json
  { "eslint": ">=9.0.0", "typescript": ">=3.3.1" }
  ```
- While ESLint 10 is technically allowed by peer dependencies, moving to `10.x` is a major version migration that should be vetted separately from scaffolding.

---

## Watch list

- **`certifi`:** Currently a dev-only transitive dependency via `httpx` for test execution. It (via `httpx` or whichever HTTP client the application adopts) becomes a runtime dependency when the backend calls an LLM provider over HTTPS (T6); re-check its version then.
- **Transitive dependency pinning:** Transitive dependencies are not pinned in `backend/pyproject.toml`. A lockfile or constraints file should be considered before any public deployment.
