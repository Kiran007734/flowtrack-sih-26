# Phase 3 readiness

## Decision

**Conditionally ready for specialist development, not operationally accepted.** Phase 3 may build on the foundation, but Docker/PostgreSQL/Redis/Celery acceptance and the audit-table permission correction are release gates.

## Verified foundation

- Versioned synthetic workflows, human-authorized draft/submission/transitions, row versions, stage history, audit/outbox records.
- Backend scope enforcement, private versioned documents, local Argon2 authentication and revocable short-lived sessions.
- Persisted idempotency for application/document/notification commands; altered key reuse is rejected.
- React shell plus application list/form/detail/timeline, upload and notifications use real APIs; TypeScript and ESLint pass.

## Failed, blocked, and known limits

- **Security gate:** runtime PostgreSQL access must be proven unable to `UPDATE` or `DELETE` `audit_events`.
- **Blocked:** no Docker, so Compose health, PostgreSQL grants/migrations, Redis/Celery processing, restart persistence and real concurrency are unexecuted.
- **Blocked:** Windows Application Control blocks `@rollup/rollup-win32-x64-msvc`; Vitest and Vite production build did not start.
- **Deliberately absent:** OCR/Copilot, deficiencies/returns/resubmission, EVC scheduling, undertakings/validity, deadlines, reports/exports, email/SMS, production IdP/MFA, malware scanning, KMS/retention.

## Constraints for Phase 3

- PostgreSQL remains authoritative; Redis must not hold business truth.
- New business commands need backend scope checks, concurrency control where mutable, persisted idempotency, audit, and transactional outbox side effects.
- Workflow rules stay `SYNTHETIC_CONFIGURATION` until governed sources verify them. AI may not transition or decide cases.
- Documents remain private and version/provenance linked.

## Problem-statement crosswalk

| Area | Foundation support | Complete feature? | Safeguard |
|---|---|---|---|
| A. End-to-end workflow automation | Versioned synthetic routes, submission, evaluator, audit/outbox. | No; scrutiny/deficiency loop is later. | Human-only, no official-route claim. |
| B. Dashboard/pendency monitoring | Stable application/status data. | No dashboard/projection. | Scope-filter aggregates. |
| C. EVC scheduling/completion | Synthetic EVC stage can exist. | No queue/calendar/outcomes. | No inferred statutory rules. |
| D. Undertaking/compliance evidence | Private versioned documents and prerequisites. | No lifecycle. | Preserve provenance. |
| E. Document expiry/renewal | Metadata and worker extension points. | No policy/reminders. | Verified policy required. |
| F. Notifications/escalation/reports | Durable in-app outbox design. | No escalation/report/export/email/SMS. | Queued is not delivered; scope reports. |

## Required infrastructure and next commands

1. Docker Engine/Compose, PostgreSQL 16, Redis 7, plus `TEST_POSTGRES_DATABASE_URL`.
2. Docker/Linux CI or an approved Rollup policy—never bypass Application Control.
3. A reviewed migration/deployment grant that makes `audit_events` insert/select-only for runtime, plus a PostgreSQL privilege regression test.

```powershell
Copy-Item .env.example .env
# Set unique POSTGRES_PASSWORD, POSTGRES_APP_PASSWORD, TOKEN_SIGNING_SECRET.
docker compose build
docker compose up -d postgres redis
docker compose run --rm --no-deps migrate
docker compose run --rm --no-deps api python -m app.db.seed
docker compose up -d api worker scheduler web
docker compose ps
Invoke-WebRequest http://localhost:8000/health/ready
docker compose exec -T worker celery -A app.tasks.celery_app:celery_app call flowtrack.diagnostic
docker compose run --rm --no-deps api pytest -q
docker compose run --rm --no-deps web npm run test -- --run
docker compose run --rm --no-deps web npm run build
```

Then run the worker-outage/restart scenario in `docs/operations/outbox.md`, prove the database grants, and update the acceptance matrix with actual results.
