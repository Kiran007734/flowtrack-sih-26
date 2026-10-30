# SIH synthetic demonstration runbook

This demonstration uses only the development seed. It is not connected to AICTE and no shown deadline, approval decision, or AI suggestion is official.

## Setup

1. Copy `.env.example` to `.env` and replace all password/token placeholders.
2. On a Docker-capable host, run the quick-start commands in the project README: start PostgreSQL and Redis, apply migrations through `0008_protect_audit_events`, run the development-only seed, then start API, worker, scheduler, and web.
3. Confirm `GET /health/ready` reports database, Redis, and private storage availability before presenting reminder delivery.

The seed is idempotent and refuses production mode. Demo accounts and the shared development-only password are documented in [local demo accounts](../implementation/local-demo-accounts.md).

## Suggested sequence

1. Sign in as `applicant.alpha@example.org`; show scoped applications, private document metadata, and the workflow timeline.
2. Sign in as `scrutiny.north@example.org`; show that scrutiny work requires an active assignment and that a different regional user is denied.
3. Use `evc.south@example.org` on the EVC workspace to show a synthetic visit lifecycle, checklist, pinned evidence version, report review, and in-app reminder history.
4. Use `compliance.south@example.org` to create/review a synthetic obligation; then use an authorized institution account to submit a specific document version. Demonstrate return with reason, resubmission, verification, validity registration, and renewal.
5. Open Pendency Dashboard as a regional user; select a case drill-down and confirm the same scoped records underlie totals.
6. Open an application as an authorized reviewer and show Grounded review assistance. State its deterministic fallback notice: no approved guidance corpus, OCR, embeddings, or LLM are running; it cannot decide or advance a case.

## Do not claim

- Email/SMS or external notification delivery.
- PostgreSQL audit-role restrictions until the runtime grant test is executed.
- Browser E2E coverage, Docker/Redis/Celery runtime coverage, OCR, semantic retrieval, LLM outputs, or official AICTE integration.
