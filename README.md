# AI Commerce OS

An AI-driven Commerce Operating System: a multi-tenant product catalog with an AI
content/image generation pipeline (human-approval gated) and a marketplace listing
pipeline, built as a Next.js frontend + FastAPI backend monorepo.

## What's built

- **Auth & multi-tenancy** — email/password signup and login (Argon2 password hashing,
  cookie sessions, CSRF double-submit protection), organizations with role-based
  membership (owner/admin/member), invitations, email verification, password reset. Every
  organization-owned query is tenant-scoped (`app/db/tenant.py`); rate limiting and
  failed-login throttling protect the auth endpoints (`app/core/rate_limit.py`).
- **Product catalog** — products, image/asset uploads, JSONB metadata for
  extensible fields like AI-generated tags.
- **AI content pipeline** — a LangGraph workflow (`analyze -> description -> title ->
  tags`) that generates product copy via a pluggable provider abstraction (Anthropic,
  Gemini, or a deterministic mock for tests), with per-task model routing, retry/backoff
  on transient provider failures, sanitized error categories, cost/token tracking per
  call (`AIRun`), and an optional per-organization monthly spend ceiling. Nothing is
  written to a product automatically — each generated field is applied independently
  only after explicit review.
- **AI image pipeline** — prompt crafting + image generation, with variations and
  regeneration support. Every AI-generated image starts `pending_review` and requires
  explicit human approval before it can be published or set as the primary image —
  enforced at the service layer, a database constraint, and the frontend, independently.
- **Marketplace listing pipeline** — draft → approve → publish → active/ended, via a
  pluggable marketplace adapter abstraction (currently a deterministic manual adapter;
  real marketplace integrations are a future phase).
- **AI Studio UI** — a frontend panel for generating, reviewing, and applying AI content
  and images per product, with full generation history (provider, model, cost, tokens,
  retries, status).

See [docs/architecture.md](docs/architecture.md) for the full picture: module
boundaries, the provider/adapter abstractions, the data model, and an explicit list of
what's deliberately **not** built yet (no MCP integration, no background job queue, no
billing enforcement, no real marketplace OAuth beyond the manual adapter).

## Structure

```
ai-commerce-os/
├── docs/           # Architecture documentation, backup/restore
├── scripts/        # backup_db.sh / restore_db.sh (see docs/backups.md)
├── frontend/       # Next.js (TypeScript, App Router)
├── backend/        # FastAPI application
│   └── app/
│       ├── api/v1/       # HTTP routing
│       ├── services/     # business logic, tenant-scoped queries
│       ├── agents/       # LangGraph workflows
│       ├── ai/            # provider abstraction, tools, pricing
│       ├── marketplaces/ # marketplace adapter abstraction
│       └── models/        # SQLAlchemy models
├── docker-compose.yml  # Local PostgreSQL for development
└── .env.example        # Env vars consumed by docker-compose
```

Every request is tagged with a correlation ID and logged as structured JSON
(`app/core/request_context.py`, `app/core/logging.py`) — see the module docstrings for
details. Database backup/restore is a documented, scripted manual process, not an
automated job (no background workers) — see [docs/backups.md](docs/backups.md).

## Prerequisites

- Node.js 20+
- Python 3.11+
- Docker (for local PostgreSQL)

## Getting started

1. Copy env files:
   - `.env.example` → `.env` (root, for docker-compose)
   - `backend/.env.example` → `backend/.env`
   - `frontend/.env.local.example` → `frontend/.env.local`
2. Start PostgreSQL: `docker compose up -d`
3. Backend:
   ```
   cd backend
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload
   ```
4. Frontend:
   ```
   cd frontend
   npm install
   npm run dev
   ```

The AI providers (Anthropic/Gemini) and the marketplace adapter work without any
external credentials in tests (everything is mocked), but running the app for real
against a live provider needs an API key set in `backend/.env` — see the comments in
`backend/.env.example` for exactly which variables matter and what an unset key does
(a clean "not configured" error, not a crash).

### Running the full stack in Docker

`docker-compose.yml` (above) stays Postgres-only, for native `--reload`/hot-reload dev.
To run the whole containerized stack instead — production-style multi-stage images for
both apps, a non-root user, migrations applied automatically on backend startup — use
the separate compose file:

```
docker compose -f docker-compose.prod.yml up --build
```

Backend on `:8000`, frontend on `:3000`. See `backend/Dockerfile`, `frontend/Dockerfile`,
and the comments in `docker-compose.prod.yml` for what each stage does and why this is a
second file rather than folded into the one above.

## Tests

```
cd backend && pytest
cd frontend && npx vitest run
```

No test in either suite makes a real network call.
