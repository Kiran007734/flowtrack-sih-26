# Final completion checklist

Last updated: 2026-10-28 (local host audit)

## Completed and verified locally

- [x] Audited the FastAPI, React/Vite, Alembic, SQLAlchemy, worker, private-storage, and test layout.
- [x] Confirmed the migration chain ends at `0014_decisions_communications`; no schema change was needed for this pass.
- [x] Added scoped/permissioned committee-member eligibility checks. A member must be active, hold `committee.review`, be in the application's scope, and be assigned while the review remains open.
- [x] Fixed outbox handling for `COMMITTEE_REVIEW_FINALIZED`, `COMPLIANCE_EVIDENCE_SUBMITTED`, and the emitted `EVC_VISIT_CANCELED` spelling so these valid events are processed rather than retried as unsupported.
- [x] Made workflow, committee, decision, communication, and application mutation handlers perform current authorization/scope checks before returning an idempotency replay. Transition replay authorization deliberately does not re-evaluate the prior command's state transition.
- [x] Completed lifecycle UI gaps: authorized transition controls, decision outcome selection, committee findings visibility and assigned-member submission, communication draft editing, permission-specific communication actions, workflow-template selection, and global audit-history visibility.
- [x] Added frontend lifecycle tests for draft editing and an assigned member's findings submission.
- [x] Added backend regression coverage that a finalized committee event is processed and that a replay is refused after the actor loses its active role grant.
- [x] Removed the committed synthetic-demo password. The guarded seed now requires a unique local `DEVELOPMENT_SEED_PASSWORD`; tests supply a test-only value.
- [x] Added and executed a guarded SQLite fallback bootstrap for hosts without Docker. It refuses existing files and is labelled as non-PostgreSQL validation.
- [x] Ran a live local synthetic lifecycle: committee finalization, decision recording, authorized workflow transition, simulated communication queueing, outbox processing, and persisted delivery state.
- [x] Added browser CORS support and regression coverage for the existing communication-draft `PUT` action.
- [x] Hardened production JWT validation to reject placeholders and values shorter than 32 characters.

## Latest validation evidence

| Area | Command | Result |
|---|---|---|
| Backend lint | `backend/.venv/Scripts/ruff.exe check app tests` | Passed |
| Backend lifecycle regression | `backend/.venv/Scripts/pytest.exe tests/integration/test_application_lifecycle.py -q` | 20 passed (warnings only) |
| Full backend suite | `backend/.venv/Scripts/pytest.exe -q` | 36 passed, 1 PostgreSQL contract test skipped because `TEST_POSTGRES_DATABASE_URL` is absent |
| Frontend lint/type-check | `npm.cmd run lint`; `npm.cmd run typecheck` | Passed |
| Frontend tests/build | `npm.cmd test`; `npm.cmd run build` | 5 tests passed; production build passed |

## Current environmental limits

- Docker/Compose is not installed on this host, so the PostgreSQL, Redis, Celery, container migration, and production-equivalent persistent stack cannot be started or verified here.
- The supported host-independent tests use SQLite and do not claim PostgreSQL compatibility. The repository's PostgreSQL contract test is correctly skipped without `TEST_POSTGRES_DATABASE_URL`.
- The `uv` default shared cache is inaccessible to this sandbox, but the project-local Python 3.12 virtual environment works.
- Vite/esbuild requires execution outside the restrictive filesystem sandbox because it resolves configuration through parent directories. Those checks were explicitly approved and succeeded.

## Current local runtime

- API: `http://localhost:8000` (SQLite fallback; HTTP 200 from `/health/ready`). The readiness payload explicitly reports Redis as unavailable.
- Frontend: `http://localhost:5173` (HTTP 200).
- Demo fallback database: `backend/local-demo.sqlite3` (ignored local artifact); private fallback storage remains outside frontend public assets.
- Persisted runtime check: the synthetic selected application is at `scrutiny`/`IN_REVIEW`; its approved communication is `SIMULATED_DELIVERED`.
- Browser preflight for `PUT /api/v1/communications/{id}` returns HTTP 200 and permits `PUT`.

## Remaining validation sequence

1. Use the guarded SQLite UI/API fallback if Docker remains unavailable; it is explicitly not PostgreSQL/worker validation.
2. On a Docker-capable host, follow `docs/operations/local-development.md`: configure `.env`, start PostgreSQL and Redis, migrate, seed, then start API, worker, scheduler, and web.
3. Verify `/health/ready`, the web UI, one authorized lifecycle journey, and queued-to-simulated-delivered communication processing against PostgreSQL/Redis.
