# Backend

FastAPI application for AI Commerce OS.

## Setup

```
cp .env.example .env
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

## Layout

- `app/api/` — HTTP routes
- `app/core/` — settings/configuration
- `app/db/` — SQLAlchemy engine/session/base
- `app/models/` — SQLAlchemy models (13 tables)
- `app/agents/` — LangGraph agent layer (placeholder, not yet implemented)
- `alembic/` — schema migrations, generated from `app/models`

## Tests

Tests run against a dedicated `ai_commerce_os_test` database (never the dev database) — create it once:

```
createdb -U postgres ai_commerce_os_test
pytest
```

`tests/conftest.py` points `DATABASE_URL` at the test database, creates all tables from `Base.metadata` directly (not through Alembic, for speed), and wraps each test in a transaction that's rolled back afterward.

## Migrations

`alembic/env.py` reads the DB URL from `app.core.config.settings` (i.e. your `.env`), so no separate Alembic config is needed.

```
alembic upgrade head        # apply all migrations
alembic revision --autogenerate -m "..."   # generate a new migration from model changes
alembic check                # confirm models and DB are in sync, no drift
alembic downgrade -1         # roll back one migration
```
