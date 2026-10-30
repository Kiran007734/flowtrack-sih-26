# Phase 4 test report

| Group | Command | Actual result |
|---|---|---|
| Backend format/lint | `ruff format app alembic tests`; `ruff check app alembic tests` | Passed. |
| Backend regression/EVC lifecycle | `pytest -q` | **20 passed, 1 skipped**. The skip requires `TEST_POSTGRES_DATABASE_URL`. EVC proposal replay, regional denial, confirm/start/complete, checklist completion, report return/resubmit/accept/close, exact-version evidence link/replay, altered-payload rejection, cross-region denial, verification, audit history, EVC evidence outbox persistence, and configured EVC prerequisites blocking then allowing a synthetic transition are covered. |
| Migration mechanics | Fresh SQLite `alembic upgrade head`; `alembic current` | Blocked at `0006_evc_evidence_and_report_lifecycle`: it uses `create_foreign_key` after table creation and Alembic SQLite raises `NotImplementedError: No support for ALTER of constraints`. Migration `0006` was not modified because it is already applied history. PostgreSQL migration validation is required. |
| Docker/PostgreSQL/Redis/Celery | Compose runbook | Blocked: Docker unavailable. |
| Frontend tests/build | `npm run lint`; `npm run typecheck`; `npm run test`; `npm run build` | Passed: lint/type-check, 2 Vitest tests, and production Vite build. No Phase 4.3 EVC workspace UI was added in this increment. |

## Completion-sprint results

| Group | Command | Actual result |
|---|---|---|
| Reminder unit test | `pytest tests/unit/test_tasks.py -q` | Passed: 3 passed. Covers same-day reminder deduplication, in-app outbox delivery, cancellation suppression, overdue escalation, and retry after a deterministic delivery-adapter failure. |
| Backend lint | `ruff check app alembic tests` | Passed. |
| Frontend validation | `npm run lint`; `npm run typecheck`; `npm run test`; `npm run build` | Passed: 2 Vitest tests and production build. |
| Backend regression partition | `pytest -q --ignore=tests/unit/test_tasks.py`; `pytest tests/unit/test_tasks.py -q` | Passed in the available host window: 19 passed, 1 PostgreSQL-only skipped; then 3 reminder/task tests passed independently. This is equivalent coverage to the 22 collected tests, but not claimed as one uninterrupted `pytest -q` process because that command exceeded the host 30-second command window. |
| Docker/Redis/Celery runtime | `docker --version`; service start | Blocked: Docker is not installed on this host, so PostgreSQL/Redis/Celery runtime delivery could not be exercised. |

## Compliance/validity sprint results

| Group | Command | Actual result |
|---|---|---|
| Compliance lifecycle | `pytest tests/integration/test_application_lifecycle.py::test_compliance_obligation_evidence_review_and_validity -q` | Passed. Covers region-scope denial, scoped creation, exact-version evidence submission, required return reason, human verification, validity registration and invalid date rejection. |
| Backend lint | `ruff check app alembic tests` | Passed. |
| Frontend | `npm run lint`; `npm run typecheck`; `npm run test`; `npm run build` | Passed: 2 Vitest tests and production build. |
| Reminder runtime | Celery task/service implementation | Implemented but not integration-tested against Redis/Celery because Docker/Redis are unavailable. Existing EVC reminder tests remain green; compliance reminder delivery needs runtime acceptance when infrastructure is available. |

## Pendency dashboard sprint results

| Group | Command | Actual result |
|---|---|---|
| Dashboard integration | `pytest tests/integration/test_application_lifecycle.py::test_pendency_dashboard_is_scoped_and_matches_drill_down -q` | Passed. Verifies region isolation, total-active agreement with drill-down cases, and stage-total agreement with the same rows. |
| Backend lint | `ruff check app tests` | Passed. |
| Frontend | `npm run lint`; `npm run typecheck`; `npm run test`; `npm run build` | Passed: lint/type-check, 2 Vitest tests, and production build. |

## Final feature-completion results

| Group | Command | Actual result |
|---|---|---|
| Final backend regression slice | `pytest` for AI-assist scope/non-binding behavior, compliance lifecycle, and dashboard scope/total consistency | Passed: 3 passed. |
| Backend lint | `ruff check app tests` | Passed. |
| Frontend | `npm run lint`; `npm run typecheck`; `npm run test`; `npm run build` | Passed: 2 Vitest tests and production build. |
| Browser E2E | Playwright discovery | Not available as a project dependency; no browser E2E result is claimed. |
| PostgreSQL/Redis/Celery/Docker | host availability check | Celery CLI is installed; Docker and Redis executables are unavailable. No PostgreSQL URL was supplied; PostgreSQL audit privilege and migration gates remain open. |

## System-acceptance results

| Group | Command | Actual result |
|---|---|---|
| Backend collection | `pytest --collect-only -q` | 26 tests collected. |
| Lifecycle integration | Five filtered `pytest tests/integration/test_application_lifecycle.py` groups | Passed: 16/16 lifecycle tests, grouped only because a single file exceeds the host 30-second command window. |
| Security/unit | `pytest tests/security tests/unit -q` | Passed: 9/9 after an idempotent temporary-storage cleanup fix in the test harness. |
| PostgreSQL contract | `pytest tests/integration/test_postgresql_contract.py -q` | Skipped: `TEST_POSTGRES_DATABASE_URL` is not configured. The test now verifies runtime `INSERT=true`, `UPDATE=false`, `DELETE=false` privileges on `audit_events`. |
| SQLite migration check | fresh `alembic upgrade head` | Fails at historical `0006` with `NotImplementedError: No support for ALTER of constraints in SQLite dialect`; `0006` is unchanged. New `0008` is PostgreSQL-only. |
| Runtime discovery | `docker --version`; `redis-server --version`; `celery --version` | Docker and Redis commands unavailable; Celery 5.5.1 installed. |

## Guidance catalogue milestone results

| Group | Command | Actual result |
|---|---|---|
| Catalogue lifecycle and mapping integration | `pytest tests/integration/test_application_lifecycle.py -k "guidance_catalogue or requirement_version" -q` | Passed: 2 passed, 16 deselected. Covers source draft/submit/approve, requirement draft/submit/approve, exact document-version mapping proposal, authorized confirmation, immutable reviewed state, cross-institution denial, audit event, mapping replacement supersession, and requirement-version supersession. |
| Backend lint | `ruff check app alembic tests` | Passed after the new catalogue models, service, routes, seed permissions and migration were formatted. |
| Frontend | `npm run lint`; `npm run typecheck`; `npm run test`; `npm run build` | Passed: lint and TypeScript checks; 3 Vitest tests passed, including the guidance workspace empty state; production build passed. Vite emitted a non-blocking >500 kB chunk-size warning. |
| Migration head | `alembic heads` | `0009_guidance_catalogue (head)`. |
| Fresh SQLite migration | `DATABASE_URL=sqlite+pysqlite:///./catalogue-migration-check.sqlite3 alembic upgrade head` | Blocked at unchanged historical `0006_evc_evidence_and_report_lifecycle` with SQLite `NotImplementedError` for foreign-key alteration. `0009` was not reached; this does not validate PostgreSQL migration behavior. |
| Current collection/security-unit regression | `pytest --collect-only -q`; `pytest tests/security tests/unit -q` | 28 tests collected; 9 security/unit tests passed. |

## Required later acceptance

## Step 3 ingestion increment results

## Step 3.1 OCR hardening results

## Step 4 retrieval status

Migration `0012_guidance_passages` is the current head. Static/frontend validation was rerun after the passage API/UI change. No real embedding model, vector database, PostgreSQL migration, Celery worker or LLM execution was available; therefore semantic retrieval accuracy and LLM evaluation are not reported.

| Area | Actual result |
|---|---|
| Digital PDF / renderer | `pypdf` per-page extraction and `pypdfium2` single-page rendering implemented; a synthetic blank PDF rendered successfully in a focused local test. |
| Scanned/mixed PDF | Per-page fallback is implemented (`OCR_PDF_RENDER`) when embedded text is below the configured threshold. It is not runtime-validated because Tesseract is missing. |
| PNG/JPEG | OCR path, image pixel limit and timeout are implemented but cannot run without Tesseract. |
| Missing executable | Focused test passed; runtime detection returned `TesseractNotFoundError`, which maps to persisted `OCR_EXECUTABLE_NOT_FOUND` processing failure. |
| Corrections | Additive migration `0011_guidance_extraction_corrections` preserves each corrected-text revision while retaining raw extraction. PostgreSQL validation remains pending. |

| Group | Command | Actual result |
|---|---|---|
| Ingestion integration | `pytest tests/integration/test_application_lifecycle.py -k guidance_ingestion -q` | Passed: 1 passed. Exercises authorization, immutable document-version pinning, durable run/audit creation and the human-review state/failure boundary. |
| Dependency installation | `uv sync --extra dev` | Passed: locked and installed `pypdf 5.4.0`, `Pillow 11.2.1`, and `pytesseract 0.3.13`. No Tesseract executable was detected or exercised. |
| Backend static check | `ruff check app tests` | Passed. |
| Backend collection | `pytest --collect-only -q` | Passed: 29 tests collected. A whole-suite run exceeded the host command window after 12 progress markers, so a complete-suite pass is not claimed. |
| Frontend | `npm run lint`; `npm run typecheck`; `npm run test -- --run`; `npm run build` | Passed: lint, TypeScript, 3 Vitest tests and production build. Build has the existing non-blocking >500 kB chunk warning. |
| Migration/runtime | Fresh SQLite migration, PostgreSQL, Redis/Celery worker and browser E2E | Not verified. Historical SQLite migration `0006` remains the documented blocking foreign-key alteration; no PostgreSQL URL, Docker/Redis runtime or browser E2E project setup is available. |

Run a Docker/PostgreSQL scenario covering concurrent schedule conflict, runtime database grants, worker dispatch of EVC events, persistence after restart, configured prerequisite transitions, reminder deduplication/suppression, and browser flows once the approved native build environment is available.
