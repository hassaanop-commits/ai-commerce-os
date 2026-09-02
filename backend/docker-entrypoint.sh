#!/bin/sh
set -e

# Run pending migrations before serving any traffic -- a fresh deployment's
# database starts with zero tables, and every DB-touching request would
# fail without this. Safe on every container start/restart: alembic is a
# no-op once the schema is already current. (The test suite deliberately
# does NOT go through this -- it creates tables via Base.metadata.create_all()
# against its own throwaway DB, see backend/tests/conftest.py -- so this is
# the only place `alembic upgrade head` actually runs against real data.)
alembic upgrade head

# exec, not a plain call: replaces this shell process with uvicorn (PID 1)
# instead of running it as a child, so it receives SIGTERM directly from
# `docker stop` and can shut down gracefully instead of being killed after
# the stop grace period waiting on a shell that never forwards the signal.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
