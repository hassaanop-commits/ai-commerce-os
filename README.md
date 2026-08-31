# AI Commerce OS

An AI-driven Commerce Operating System. This repository is a monorepo containing the frontend, backend, agent layer, and shared documentation.

## Structure

```
ai-commerce-os/
├── docs/           # Shared documentation
├── frontend/       # Next.js (TypeScript, App Router)
├── backend/        # FastAPI application
│   └── app/agents/ # LangGraph agent layer (placeholder, not yet implemented)
├── docker-compose.yml  # Local PostgreSQL for development
└── .env.example        # Env vars consumed by docker-compose
```

See [docs/architecture.md](docs/architecture.md) for how the layers fit together.

## Status

This is the initial scaffold only. No business logic, agents, marketplace integrations, or authentication have been implemented yet. No dependencies have been installed.

## Prerequisites

- Node.js 20+
- Python 3.11+
- Docker (for local PostgreSQL)

## Getting started (once you're ready to run things)

1. Copy env files:
   - `.env.example` → `.env` (root, for docker-compose)
   - `backend/.env.example` → `backend/.env`
   - `frontend/.env.local.example` → `frontend/.env.local`
2. Start PostgreSQL: `docker compose up -d`
3. Backend: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
4. Frontend: `cd frontend && npm install && npm run dev`
