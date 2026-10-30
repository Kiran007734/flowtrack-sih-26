# Testing Strategy

## Quality approach

Testing proves the architecture's safety properties first: scope isolation, human-only transitions, durable side effects, document privacy, provenance, and graceful AI degradation. Synthetic fixtures are the default; no real institutional documents or credentials are committed.

| Layer | Tools | Focus | Examples |
|---|---|---|---|
| Python unit | Pytest | pure policy/fact evaluators, validators, state machines, date calculations | transition explanation, prerequisite expression, expiry calculation |
| Repository/domain integration | Pytest + ephemeral PostgreSQL | constraints, transactions, scoped repositories, audit/outbox | cross-institution query denial, submitted snapshot immutability |
| API integration | FastAPI test client + real test DB/Redis where relevant | auth, schemas, permission decisions, idempotency/errors | assigned officer can return; unrelated officer receives 404/403 |
| Worker integration | Celery test worker + Postgres | retry, idempotence, OCR/deadline/outbox behavior | Redis outage leaves DB outbox then exactly-once logical delivery |
| Frontend unit/component | Vitest + React Testing Library | route guards, forms, accessible components, API states | blocked-transition reasons render; Zod form errors announced |
| Browser end-to-end | Playwright against Compose | critical role journeys and downloads | applicant submit → deficiency → correction → resubmission |
| Contract | OpenAPI schema validation/client generation checks | frontend/API compatibility | a breaking response fails CI |
| Security | SAST/dependency/secret scan plus custom integration tests | authorization, injection, file paths, headers | IDOR, CSRF, upload type/path traversal |
| Performance/resilience | k6/Locust selected later; Compose fault tests | workload targets and dependency loss | stop worker/Redis; backlog recovery, concurrent transition conflict |
| AI evaluation | versioned synthetic dataset | grounding/ACL/accuracy/regression | prompt injection, forbidden decision request, citation recall |

## Critical acceptance scenarios

1. An applicant at Institution A cannot read, enumerate, download, or mutate any Institution B record.
2. A regional role with Region A grant cannot access Region B merely by possessing the role.
3. A scrutiny officer cannot transition an unassigned case; an assigned officer still cannot bypass template prerequisites.
4. Every allowed command produces exactly one logically correlated audit event and outbox event; failed transactions produce neither.
5. A return/resubmission preserves original submitted version, deficiency, responses, reviewers, and transition chronology.
6. Worker and Redis interruption retains notifications/deadlines in Postgres; restoring service results in retry without duplicate user-visible notice.
7. Document content is inaccessible from a public URL and is checked on every download; replacing a document creates a new version.
8. Template publication rejects invalid graphs; in-flight applications retain their original template version.
9. OCR/LLM offline does not stop upload, manual review, normal stage completion, or source browsing.
10. Copilot only cites sources the caller can access, labels uncertainty/synthetic sources, and refuses an approval/rejection request.

## Traceability test catalogue

These are Phase 2 test identifiers and acceptance definitions, not a claim that automated tests already exist.

| ID | Automated acceptance definition |
|---|---|
| T-01 | A principal scoped to Institution A cannot list, retrieve, mutate, or download Institution B records, including guessed IDs. |
| T-02 | A regional principal granted Region A cannot access Region B; adding a Region B grant changes access only after server-side authorization refresh. |
| T-03 | Submitting an application creates an immutable version/snapshot; an attempted mutation creates a permitted new draft/version or is rejected. |
| T-04 | An allowed state-changing command writes its business change, audit event, and outbox event atomically; a failed transaction writes none. |
| T-05 | An unassigned scrutiny officer cannot review/return a case; an assigned officer may only perform template-authorized actions. |
| T-06 | A deficiency return, correction response, verification, and resubmission preserve all historical versions and transition ordering. |
| T-07 | Document blobs have no public route; a cross-scope caller is denied, and a replacement creates a distinct immutable version. |
| T-08 | Invalid template graphs/source metadata cannot publish; a submitted case remains bound to the template version selected at submission. |
| T-09 | EVC scheduling rejects overlapping personnel/slot constraints and rejects a coordinator outside the visit's scope. |
| T-10 | A panel review record can only be submitted by an assigned member; its recommendation cannot independently finalize a case. |
| T-11 | An undertaking configured as a prerequisite blocks the transition until correct evidence and authorized verification exist. |
| T-12 | Validity expiry/renewal alerts use recorded provenance, and OCR-derived dates remain unverified until human confirmation. |
| T-13 | Stop Redis/worker after the database transaction, restore them, and assert backlog replay plus one logical notification/delivery record. |
| T-14 | Dashboard/report queries and exports contain only authorized scope; export creation and download appear in audit history. |
| T-15 | Runtime database credentials cannot update/delete audit events; the audit-chain verifier detects an injected discontinuity in a controlled test. |
| T-16 | OCR failure or low confidence leaves the source document/manual path usable and the normal workflow available. |
| T-17 | AI-proposed evidence starts `PROPOSED`; only an authorized human can confirm it, with source/document versions retained. |
| T-18 | Copilot adversarial tests prove ACL filtering, citation-only grounding, uncertainty for missing evidence, and refusal of approval/rejection actions. |
| T-19 | Validation Center seeds/runs are synthetic-labelled and production-mode attempts are rejected. |
| T-20 | Liveness/readiness and diagnostics distinguish database/storage failure, Redis degradation, and optional AI unavailability without leaking secrets. |
| T-21 | Keyboard/form-error/screen-reader component checks and critical Playwright accessibility smoke pass. |
| T-22 | Export artifacts expire/are access-controlled and retain checksum/requester/audit provenance. |
| T-23 | Future verified-source publication requires source version, verifier, and sign-off before a configuration can lose synthetic labelling. |
| T-24 | Future production adapters pass contract tests, retention-policy tests, and backup/restore drills before use with real data. |

## Test data and environments

Fixture factories create two regions, multiple institutions, role/scope combinations, every route template, overdue/future deadlines, clean/low-confidence documents, and both verified/synthetic catalogue sources. Test database migrations run from empty to head. Test storage is isolated per run and cleaned safely by the test harness. The Validation Center provides reusable stakeholder demo scenarios but is distinct from developer test fixtures.

## CI quality gates

On pull request: formatting/linting/type checks; backend/frontend unit tests; migration-up/down validation; API integration; dependency/secret scan; OpenAPI diff; and selected Playwright smoke. Nightly: full browser, fault-injection, larger synthetic corpus/OCR, and AI regression tests. Releases require migration review, all critical acceptance scenarios green, no unresolved high-severity security finding, and explicit confirmation that rule content is synthetic or source-verified.

## Coverage and reporting

Set thresholds after baseline implementation, prioritizing branch coverage of authorization and transition evaluators rather than a misleading global number. Report test case IDs referenced in `requirements-traceability.md`, source/template/model versions, and failure artifacts (sanitized logs, screenshots, traces) for reproducibility.
