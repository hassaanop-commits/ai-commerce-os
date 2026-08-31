# Architecture

## Layers

- **frontend/** — Next.js app (TypeScript, App Router). Talks to the backend over HTTP via `NEXT_PUBLIC_API_URL`.
- **backend/** — FastAPI application. Exposes the HTTP API consumed by the frontend and owns all database access.
  - **backend/app/agents/** — LangGraph agent layer, nested inside the backend since agents run in-process with the API today. No agents are implemented yet; this is a placeholder package. If agent workloads later need independent scaling, this package can be extracted into its own service without disrupting the rest of the backend.
- **PostgreSQL** — the system of record, run locally via `docker-compose.yml`. The backend connects to it through SQLAlchemy (`app/db/`).

## Data flow (target)

```
frontend  -->  backend API (app/api/)  -->  agents (app/agents/)  -->  PostgreSQL (app/db/)
```

Today only the HTTP skeleton and DB session plumbing exist — no agents, no business logic.

## Module boundaries

- `app/api/` — HTTP routing only; no business logic.
- `app/core/` — configuration/settings.
- `app/db/` — SQLAlchemy engine, session, declarative base.
- `app/agents/` — LangGraph graphs/nodes (future).
