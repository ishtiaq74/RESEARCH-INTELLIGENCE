# Research Intelligence — Frontend

Next.js 16 (App Router) + TypeScript frontend skeleton.

## Requirements

- Node.js 20+
- npm 10+
- Backend running (see `../backend/`)

## Setup

```bash
npm install
cp .env.example .env.local
# Edit .env.local: set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Run

```bash
npm run dev     # http://localhost:3000
```

## Checks

```bash
npm run lint        # ESLint
npm run type-check  # tsc --noEmit
npm run build       # production build
```
