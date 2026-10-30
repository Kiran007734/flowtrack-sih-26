# Local development

## Prerequisites

- Docker Desktop/Engine with Compose v2 (required for the complete PostgreSQL, Redis, API, worker, scheduler, and web stack).
- A copy of `.env.example` named `.env`, with unique local values for `POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD`, and `TOKEN_SIGNING_SECRET`.
- Do not use the sample values outside a local, synthetic demonstration.

The host used to author Phase 2 did not have Docker installed, so the commands below are the reproducible runbook—not evidence that Compose was successfully run there.

## Start the complete stack

PowerShell:

```powershell
Copy-Item .env.example .env
# Edit .env: replace POSTGRES_PASSWORD, POSTGRES_APP_PASSWORD, TOKEN_SIGNING_SECRET, and DEVELOPMENT_SEED_PASSWORD.
docker compose build
docker compose up -d postgres redis
docker compose run --rm --no-deps migrate
docker compose run --rm --no-deps api python -m app.db.seed
docker compose up -d api worker scheduler web
docker compose ps
```

The migration step is deliberately controlled. API replicas do not independently run migrations at startup. The initialization owner creates the separate, non-superuser `POSTGRES_APP_USER`, which is used by API, worker, and scheduler only. The short-lived `migrate` service uses the initialization owner to create schema objects; its default grants give the runtime account data access but no schema-creation privilege.

The PostgreSQL initialization script runs only for a new, empty `postgres_data` volume. If this project was previously started with an earlier local role layout, back up anything needed and intentionally reset that local volume before relying on the new privilege boundary.

Endpoints after healthy startup:

| Service | URL |
|---|---|
| Frontend | `http://localhost:5173` |
| API | `http://localhost:8000/api/v1` |
| OpenAPI/Swagger UI | `http://localhost:8000/docs` |
| Liveness | `http://localhost:8000/health/live` |
| Readiness | `http://localhost:8000/health/ready` |

## Common commands

```powershell
docker compose logs -f api worker scheduler web
docker compose run --rm --no-deps api pytest
docker compose run --rm --no-deps api ruff check .
docker compose run --rm --no-deps web npm run lint
docker compose run --rm --no-deps web npm run typecheck
docker compose run --rm --no-deps web npm run test -- --run
docker compose run --rm --no-deps web npm run build
docker compose exec -T worker celery -A app.tasks.celery_app:celery_app call flowtrack.diagnostic
docker compose down
```

Equivalent shortcuts are provided by `make` on Unix-like hosts. `make migrate`, `make seed`, and `make up` follow the same controlled order.

## Verify a local environment

1. `docker compose ps` reports healthy `postgres`, `redis`, and `api`; worker/scheduler/web should be running.
2. `Invoke-WebRequest http://localhost:8000/health/ready` reports dependency status without a connection string or secret.
3. Sign in with a documented synthetic account and create/submit a draft for its own institution.
4. Query notifications after the worker processes the submission event.
5. Stop and restart the worker, then use the outbox runbook to verify pending events replay without duplicate notifications.
6. Run `docker compose down`, then `docker compose up -d postgres redis`; confirm the named PostgreSQL volume retains seeded records before continuing.

## Private files and teardown

The browser never mounts `private_storage`; the named `private_storage` volume is available only to API/worker containers. `docker compose down` preserves named volumes. Deleting volumes (`docker compose down -v`) destroys local synthetic database and file data, so use it only when deliberately resetting a local development environment.

## Host-only development

The project targets Python 3.12. The authoring host has Python 3.11.9, so Docker is the supported way to run backend integration services. Host-only Python checks may be useful for syntax/unit validation but are not a replacement for PostgreSQL-backed integration tests.

### Guarded SQLite demonstration fallback

When Docker is unavailable but a project-local Python 3.12 virtual environment exists, the repository includes a **development-only** SQLite demo bootstrap. It creates a new, explicitly named SQLite file from the current ORM metadata and seeds synthetic data; it does **not** run Alembic because revision `0006` uses a PostgreSQL-style constraint alteration that SQLite does not support. This fallback is for UI/API demonstrations only. It does not validate the PostgreSQL migration chain, PostgreSQL locking behavior, Redis, Celery, or the container deployment topology.

From `backend` in PowerShell, choose a new filename; the command refuses to overwrite an existing database:

```powershell
$env:DATABASE_URL = "sqlite+pysqlite:///./local-demo.sqlite3"
$env:ENVIRONMENT = "development"
$env:ENABLE_DEVELOPMENT_SEED = "true"
$env:DEVELOPMENT_SEED_PASSWORD = Read-Host "Choose a unique local synthetic seed password"
$env:PRIVATE_STORAGE_ROOT = "../storage/private-local-demo"
.\.venv\Scripts\python.exe -m app.db.local_demo
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend from `frontend` in a separate terminal:

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

The seed prints only record counts. Consult the separately maintained local demo accounts document when sign-in is needed; do not place credentials in shell history or reports.

### Local account requests

The `/signup` page submits an account request to the live API. It creates an inactive user with no role assignment or institution/region scope, so it cannot sign in or access records until an administrator independently verifies the request, activates the account, and grants an appropriate least-privilege scoped role. Public registration cannot select any role or scope and is rate-limited. The prototype does not include a public account-approval screen; do not activate accounts by directly editing a shared or production database.

### Administrator user management

After applying migration `0015_user_registration_status`, an authenticated account with the existing globally scoped `SYSTEM_ADMINISTRATOR` role can open `/user-management`. This workspace lists pending requests, approves/rejects them, controls activation, and manages only validated non-system role grants. The development seed already includes a synthetic system-administrator account; its password is the local `DEVELOPMENT_SEED_PASSWORD` chosen during seeding and is never committed or printed.

For Compose development, run the existing controlled migration command before starting/restarting the API:

```powershell
docker compose run --rm --no-deps migrate
docker compose up -d api web
```

The guarded SQLite fallback intentionally does not run Alembic. For an existing guarded local demo, after creating a verified backup and stopping its project-owned API process, apply the narrow idempotent Phase 1 upgrade instead:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.db.local_demo_upgrade --database local-demo.sqlite3
```

It adds only the missing `users.registration_status` column, defaults all existing rows to `APPROVED`, and prints `already_current` if rerun. It does not recreate the database, seed data, or emulate the PostgreSQL migration chain. Do not alter an existing SQLite demonstration database directly to bypass approval or role-assignment controls.
