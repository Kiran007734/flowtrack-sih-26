# Phase 2.1 acceptance matrix

**Audit date:** 2026-10-27. `PASS` means the cited check actually ran; `BLOCKED` needs an unavailable external runtime; `NOT IMPLEMENTED` is intentionally outside the Phase 2 foundation; `FAIL` is a verified gap.

| ID | Requirement | Source/module | Test or command | Actual result | Status | Evidence / required fix |
|---|---|---|---|---|---|---|
| A | Typed configuration and safe startup defaults | `core/config.py`, `main.py` | Test suite and source review | Typed settings, safe problem responses and readiness route exist. | PASS | Docker startup remains blocked. |
| B | Clean migration and revision chain | Alembic `0001`, `0002` | Fresh SQLite `alembic upgrade head` | Reached `0002_command_idempotency`. | PASS | SQLite proves mechanics, not PostgreSQL semantics. |
| C | PostgreSQL least-privilege runtime role | Compose/init role script | Static Compose review | Runtime uses `POSTGRES_APP_USER`; `migrate` uses owner only. | BLOCKED | Verify schema ownership/grants with fresh PostgreSQL. |
| D | Auth and token/session lifecycle | `services/auth.py` | Security/API tests | Generic failures, disabled user rejection, logout revocation passed. | PASS | Bearer session; refresh rotation/MFA deferred. |
| E | Backend RBAC/ABAC | `permissions/access.py` | API integration tests | Scope/permission denials passed. | PASS | Host tests use SQLite. |
| F | Institution/region isolation | App/document services | API integration tests | Cross-scope application/document and regional reads returned 403. | PASS | Backend-enforced. |
| G | Versioned workflow/authorized transitions | Workflow models/service | Lifecycle tests/source review | Bound version, roles and prerequisites are evaluated. | PASS | Return/resubmission is Phase 3 work. |
| H | Stage history and audit integrity | Audit service/models | Lifecycle tests/source review | History/audit records are transactionally created with hash links. | FAIL | Runtime default grants do not yet DB-enforce audit insert-only behavior; add/verify PostgreSQL revoke migration. |
| I | Idempotency behavior | Command ledger/router | Backend regression tests | Same request replays; changed payload/key returns `409`. | PASS | Covers application/document/notification commands; PostgreSQL races remain blocked. |
| J | Transactional notification outbox | App/outbox services | Lifecycle and rollback tests | Submission/audit/outbox are atomic; host dispatch is deduplicated. | PASS | Real worker/Redis restart exercise blocked. |
| K | Private document storage/access | Documents/storage | Security/API tests | Generated keys, MIME/size/checksum and cross-tenant download denial passed. | PASS | Malware scanning is not implemented. |
| L | Redis and Celery | Celery/Compose | Static review | Redis is broker/result coordination only. | BLOCKED | Docker/Redis unavailable. |
| M | Scheduler uniqueness/retry | Tasks/Compose | Static review | One Beat service plus stale-claim recovery configured. | BLOCKED | No live Celery execution. |
| N | Repeatable safe seed | `db/seed.py` | Fresh SQLite seed twice | Each run: 3 apps, 2 institutions, 2 regions, 7 users. | PASS | 4 workflow versions present; production guard needs deployment validation. |
| O | Frontend build/tests | `frontend/` | npm checks | Typecheck/lint pass; test/build cannot start. | BLOCKED | Application Control blocks Rollup native binding. |
| P | API contract/errors | Schemas/router/main | OpenAPI assertion | OpenAPI 3.1, 22 paths, idempotency header verified. | PASS | Problem-shaped errors are implemented. |
| Q | Logging/secrets/security defaults | Config/main/Compose | Source/secret review | JSON logs, safe `.env.example`, private volume. | FAIL | Audit privilege gap in H is a release security gate; demo password is intentional development-only seed data. |
| R | Docker health/restart/persistence | Compose/runbook | Docker availability check | Docker command unavailable. | BLOCKED | Cannot simulate runtime success. |
| S | Requirement traceability | Traceability docs | Documentation audit | Foundation/future scope is mapped. | PASS | Phase 3 crosswalk distinguishes support from feature completion. |

## Blocked prerequisites

- Docker Engine/Compose with a fresh PostgreSQL 16 volume and Redis 7.
- A real PostgreSQL test URL in `TEST_POSTGRES_DATABASE_URL` for locking, grants, and concurrent idempotency tests.
- Docker/Linux CI or an approved native Rollup allow rule. Do not bypass Windows Application Control.
