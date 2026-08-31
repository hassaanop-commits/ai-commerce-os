# Database backups

There is no automated backup job in this codebase (per the "no background workers"
guardrail — see [architecture.md](architecture.md#non-goals)). What exists instead is a
tested, working escape hatch: two scripts to take and restore a Postgres dump by hand,
plus this doc explaining what a real deployment needs on top of them.

## Scripts

- **`scripts/backup_db.sh`** — dumps the database with `pg_dump`, gzips it, and writes
  it to `backups/<db-name>_<UTC timestamp>.sql.gz`.
- **`scripts/restore_db.sh`** — drops and recreates the target database, then restores
  it from a `.sql.gz` (or plain `.sql`) file produced by the backup script.

Both connect directly to Postgres over TCP (`localhost:5432` by default) rather than
going through `docker compose exec`. This reaches the database either way the project
runs it — `docker-compose.yml` publishes that port from the `postgres` container, and
it's the same port a native/local Postgres install listens on — so the same two scripts
work regardless of how Postgres itself happens to be running. The only requirement is
having the `postgresql-client` tools (`pg_dump`, `psql`, `createdb`, `dropdb`) and
`gzip` on `PATH`; both are typically already present if you have a full Postgres
install, or installable separately (e.g. `apt install postgresql-client`,
`brew install libpq`).

Plain SQL rather than `pg_dump`'s custom (`-Fc`) binary format is used deliberately:
restoring then needs nothing beyond `psql`, not `pg_restore` too — one fewer tool that
has to be present and working when this escape hatch actually needs to be used. The
tradeoff is a somewhat larger file and no selective/parallel restore; if that ever
matters, switching `backup_db.sh` to `-Fc` and `restore_db.sh` to `pg_restore` is a
small, self-contained change.

Connection settings come from the repo root's `.env` (`POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` — the same file `docker-compose.yml`
reads) if it exists, or fall back to `docker-compose.yml`'s own defaults
(`postgres`/`postgres`/`ai_commerce_os`/`5432`). Standard libpq env vars
(`PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`) always take precedence over both, if set.

## Taking a backup

```
bash scripts/backup_db.sh
```

Writes `backups/ai_commerce_os_<timestamp>.sql.gz`. `backups/` is gitignored — dump
files can contain real data and must never be committed.

To back up a different database (e.g. before a risky local migration test), override
`POSTGRES_DB` for that one invocation:

```
POSTGRES_DB=some_other_db bash scripts/backup_db.sh
```

## Restoring a backup

```
bash scripts/restore_db.sh backups/ai_commerce_os_20260101_120000.sql.gz
```

This is **destructive**: it drops and recreates the target database first, so anything
currently in it is lost. It asks for typed confirmation (`yes`) before doing anything;
pass `-y`/`--yes` to skip that for non-interactive use. Stop the app (`uvicorn`, and
anything else holding a connection) first — an open connection to the target database
can block the drop.

If the backup predates a migration that's since landed, run `alembic upgrade head` from
`backend/` right after restoring.

## Running a restore drill

A backup you've never restored is a hope, not a plan. Point `POSTGRES_DB` at a
throwaway name to restore into a scratch database instead of overwriting anything real,
and confirm the data actually came back:

```
POSTGRES_DB=ai_commerce_os_restore_drill bash scripts/restore_db.sh --yes backups/<file>.sql.gz
psql -h localhost -U postgres -d ai_commerce_os_restore_drill -c "SELECT count(*) FROM products;"
```

Worth doing once after setting this up, and again any time the backup/restore scripts
themselves change.

## What a real deployment needs beyond this

This gives you a manual, tested escape hatch — it is not disaster-recovery
infrastructure. A real deployment additionally needs, roughly in priority order:

1. **A schedule.** Something needs to run `backup_db.sh` (or the managed-Postgres
   equivalent below) on a recurring cadence. That's intentionally not built here — it
   would be a background job/scheduler, which is out of scope per the project's
   "no background workers" guardrail. In practice this means either:
   - Using your hosting provider's managed Postgres backups (RDS/Cloud SQL/Supabase/etc.
     all have this built in and automated snapshots are usually the better answer than
     a hand-rolled script once you're on managed Postgres anyway), or
   - A cron job / systemd timer / CI scheduled workflow on whatever host runs Postgres,
     calling this same `backup_db.sh` script.
2. **Off-host storage.** `backups/` on the same machine as the database is not a
   backup — it's a copy that dies with the same disk. A real setup uploads each dump to
   somewhere else (S3/GCS/etc.) as part of the same job and prunes local copies.
3. **Retention.** Decide how long to keep dumps (e.g. daily for 2 weeks, weekly for 3
   months) and enforce it in the same job — unbounded retention is its own cost/ops
   problem.
4. **Monitoring the backup job itself.** A silently-failing backup job is worse than an
   honestly-absent one, because it creates false confidence. The job needs to alert on
   failure, not just log it.
5. **Periodic restore drills**, as above — automated ones ideally, so "restoring
   actually works" isn't only checked when someone remembers to.

None of the above is built here; this doc exists so the gap is a documented, deliberate
decision rather than a silent one.
