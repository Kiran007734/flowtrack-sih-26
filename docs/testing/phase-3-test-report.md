# Phase 3 test report

**Status:** host-level implementation checks completed; Docker/PostgreSQL/Redis/Celery/browser-native verification remains blocked as described below.

| Group | Command | Actual outcome |
|---|---|---|
| Backend format/lint | `ruff format app alembic tests`; `ruff check app alembic tests` | Passed. |
| Backend lifecycle/security | `pytest -q` | **16 passed, 1 skipped**. The skip requires `TEST_POSTGRES_DATABASE_URL`; tests cover assignment eligibility, unassigned/revoked reviewer denial, documented return, deficiency response, resubmission, timeline, idempotency, document isolation, and rollback. |
| Migration mechanics | Fresh SQLite `alembic upgrade head`; `alembic current` | Reached `0004_reviewer_assignments (head)`. This is not PostgreSQL proof. |
| Frontend static checks | `npm run typecheck`; `npm run lint` | Passed. |
| Frontend tests/build | `npm run test`; `npm run build` | Blocked before execution: Windows Application Control blocks `@rollup/rollup-win32-x64-msvc`. |
| Docker/PostgreSQL/Redis/Celery | Docker Compose runbook | Blocked: `docker` command unavailable on this host. |

## Still required for acceptance

Run the Docker-backed lifecycle against PostgreSQL, prove runtime audit-table grants prohibit update/delete, execute concurrent idempotency/transition tests, process the returned-application outbox notification through Celery, and run Vitest/Vite on Docker or approved Linux CI.
