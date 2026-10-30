# AICTE FlowTrack

AICTE FlowTrack is a synthetic-data prototype for SIH 2026 Problem Statement 26262: an integrated workflow foundation for technical-institution approval applications, compliance monitoring, and alerts.

It is **not** connected to AICTE, contains no official approval rules or deadlines, and never lets AI approve/reject applications or silently change an official workflow state. All seeded workflow configurations are labelled synthetic.

## Implemented prototype scope

- React/Vite strict-TypeScript application shell and initial application screens.
- FastAPI `/api/v1` backend with local-development authentication and backend-enforced role/scope checks.
- PostgreSQL/SQLAlchemy/Alembic data foundation, including applications, workflow versions/history, audit events, outbox events, document metadata, and notifications.
- Private local document-storage adapter; files are never placed in the frontend public directory.
- Durable PostgreSQL outbox for in-app notifications, with Celery/Redis worker coordination.
- Synthetic, development-only seed data and data-driven application workflow, scrutiny/correction, EVC, compliance, validity, reminders, and scoped pendency dashboard.

OCR, semantic retrieval, LLM/Copilot, approved guidance corpus, official integrations, email/SMS delivery, and statutory rule content are not implemented. The displayed AI-review fallback is deterministic, read-only, and explicitly non-binding.

## Quick start

Read [local development instructions](docs/operations/local-development.md), then in PowerShell:

```powershell
Copy-Item .env.example .env
# Set unique local POSTGRES_PASSWORD, POSTGRES_APP_PASSWORD, TOKEN_SIGNING_SECRET,
# and DEVELOPMENT_SEED_PASSWORD values in .env.
docker compose build
docker compose up -d postgres redis
docker compose run --rm --no-deps migrate
docker compose run --rm --no-deps api python -m app.db.seed
docker compose up -d api worker scheduler web
```

| Endpoint | Address |
|---|---|
| Web application | `http://localhost:5173` |
| API | `http://localhost:8000/api/v1` |
| API docs | `http://localhost:8000/docs` |
| Health | `http://localhost:8000/health/ready` |

See [local demo accounts](docs/implementation/local-demo-accounts.md) only after running the development seed command.

## Development commands

```text
make build             Build images
make migrate           Apply Alembic migrations
make seed              Add idempotent synthetic development data
make up                Start the complete stack
make backend-test      Run backend tests
make frontend-test     Run frontend tests
make frontend-lint     Run frontend ESLint
make frontend-typecheck Run TypeScript checking
make frontend-build    Produce a production frontend build
```

The host used during Phase 2 authoring has no Docker executable. Docker-specific results must be validated on a Docker-capable host; this limitation is recorded in the Phase 2 test report rather than masked.

## Security and operating boundaries

- PostgreSQL is authoritative. Redis is cache/broker coordination only.
- The backend, not the UI, enforces institution/region/assignment scope.
- State changes create audit and outbox records in the same transaction.
- Local-development passwords are hashed. Never commit `.env`, production credentials, private documents, or database dumps.
- The Phase 2 local storage adapter is private but does not provide a configured malware scanner, KMS, retention policy, or compliance certification.

Architecture decisions are in [docs/architecture](docs/architecture/). The reproducible synthetic walkthrough is in [SIH demo runbook](docs/operations/sih-demo.md). Outbox recovery is documented in [outbox operations](docs/operations/outbox.md).
