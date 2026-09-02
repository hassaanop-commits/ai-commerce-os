# syntax=docker/dockerfile:1

# ---- build stage -----------------------------------------------------------
# Installs dependencies into an isolated venv. Only this stage has a C
# compiler -- the final stage below copies just the resulting venv, not this
# layer, so the shipped image never carries build tools.
FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- runtime stage -----------------------------------------------------------
FROM python:3.11-slim AS runtime

# Non-root: the app never needs root once dependencies are installed and
# code is copied in.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Only what's needed to run: application code, migrations, and the alembic
# config that points at them. No tests/, no .venv, no .env, no .git -- see
# .dockerignore. local_storage_path (app/core/config.py) defaults under
# var/storage/; a real deployment should mount a volume there instead of
# relying on this directory living inside the image, the same way it should
# point DATABASE_URL at a real Postgres instance rather than the
# docker-compose default.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh && mkdir -p var/storage && chown -R app:app /app

USER app

EXPOSE 8000

# Runs `alembic upgrade head` then execs uvicorn -- see docker-entrypoint.sh.
ENTRYPOINT ["./docker-entrypoint.sh"]
