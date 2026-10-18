# PROJECT BRIEF — Research Intelligence RAG

## What it is
A multi-document academic research workspace. Users create projects, upload academic PDFs, ask questions across papers, and get evidence-grounded answers with citations they can inspect back to the exact page and passage.

## Primary differentiator
Verifiable academic evidence, not merely conversational answers about PDFs.

## Roles
- Owner (Rahat): final decisions; relays messages between the architect and the builder.
- Claude: lead architect / technical lead. Designs, reviews evidence, writes tasks. Cannot see this repo directly.
- Antigravity: implementation agent. Builds in small steps and reports with evidence.

## MVP priorities (in order)
1. PDF upload and processing
2. Multi-document Q&A
3. Verifiable citations
4. Citation inspection (open PDF at page and highlight passage)
5. Basic paper comparison
6. Literature review drafting
7. Collection search and polish

## Decisions already made
- Scanned PDFs are rejected in the MVP with a clear error message (no OCR yet).
- Provisional limits (configurable): 20 MB per PDF, 20 papers per project, 300 pages per PDF.
- Email + password sign-in via an open-source library. No university SSO.
- Private by default. No public sharing.
- If documents don't support an answer, the system says so. No general-knowledge fallback.
- Light theme only.
- Zero-cost build.

## Quality bar
A feature is done only when behavior is implemented, tests pass, failure cases are handled, project isolation holds, and docs are updated. A working demo is not production-ready.
