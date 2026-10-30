# Module Specification

Each command below runs inside a database transaction, performs backend authorization and validation, appends an audit event, and emits durable outbox events. `GET` endpoints enforce the same record scope.

| Module | Responsibilities and data ownership | Inputs → outputs / API surface | Dependencies and failure handling |
|---|---|---|---|
| Authentication and sessions | Local/dev credentials or external IdP adapter; password/session/token records, refresh-token families, revocation | credentials → access/refresh/session; `POST /auth/login`, `/refresh`, `/logout`, `GET /me` | IAM; rate-limit login, revoke on reuse, generic failure response; never stores raw passwords/tokens |
| Users, roles, institutions, regions | users, memberships, role grants, region/institution scope; institution/region registry | admin commands → scoped principals; `/users`, `/roles`, `/institutions`, `/regions` | Auth; deny by default, reject overlapping invalid scopes, require at least one active owner/admin before removal |
| Applications | draft and submitted application aggregate, applicant-entered profile, immutable submitted snapshots | create/edit/submit → application/version; `/applications`, `/:id/submit` | IAM, documents, workflow; immutable submitted version, reject edits after submission, concurrency conflict returns 409 |
| Workflow templates and engine | versioned templates, stages, transitions, prerequisites, policies, instances/history | evaluate/request transition → allow/block explanation and transition history; `/workflow-templates`, `/applications/:id/transitions` | Apps, IAM, specialist records; never hardcodes route; inactive/ambiguous template blocks with actionable reason |
| Scrutiny and assignments | scrutiny case, assignment, review item, review record | assign/review/return → review state, findings; `/scrutiny-cases`, `/assignments`, `/reviews` | Workflow, docs, evidence; unauthorized reviewer/expired assignment blocked; reassignment audited |
| Deficiencies | deficiency, response, correction evidence, return/resubmission linkage | raise/respond/verify/close → deficiency lifecycle; `/deficiencies`, `/:id/responses` | Scrutiny, workflow, docs; closed records are append-only corrections; invalid return path rejected |
| Documents | document asset, version, hash, metadata, ACL, retention marker, scan status | upload/version/download metadata → private document handle; `/documents`, `/:id/content` | Storage adapter, IAM; checksum/type/size validation, upload quarantine, missing blob marked unavailable and audited |
| OCR and extracted text | job, page extraction, confidence, human correction, processor version | job request → extraction artifact; `/documents/:id/ocr`, `/ocr-jobs` | Documents, worker; failed/low confidence needs manual review; never overwrites source/verified metadata |
| Requirement catalogue and handbook | source documents, versioned passages, requirement definitions, applicability rules, verification status | catalogue edit/publish → current version; `/requirements`, `/handbook-sources` | IAM, docs; no delete of referenced version; unverified data visibly labelled synthetic |
| Requirement-to-evidence mapping | evidence map, candidate match, reviewer confirmation, rationale | map/confirm/reject → traceable link; `/evidence-mappings` | Requirements, docs, OCR; AI candidates remain `PROPOSED`; only authorized human may confirm |
| EVC | queue item, visit, slots, assignments, outcome/report | enqueue/schedule/record outcome → visit state; `/evc-queue`, `/evc-visits` | Workflow, calendar policy, docs; conflicts prevent scheduling; unavailable member/rejected outcome leaves workflow unchanged |
| Configurable review stages | stage-specific panel/reviewer assignments, deliberation, recommendation record | assign/recommend/record → review record; `/review-stages`, `/panel-reviews` | Workflow, IAM; recommendation is not automatic decision; quorum/rules are template configuration |
| Undertakings | undertaking, evidence, reviewer verification, status/history | issue/respond/verify → obligation state; `/undertakings` | Apps, docs, deadlines; expiry/insufficient evidence blocks closure when template requires it |
| Validity and renewals | validity record, provenance, expiry date, renewal submission/link | record/renew → current validity projection; `/validity-records` | Docs, deadlines; parses/flags dates as unverified until human confirms; never asserts legal validity from OCR alone |
| Deadlines, notification, escalation | deadline instances, policy versions, notifications, delivery attempts, escalation records | policy scan/send → durable alert/escalation; `/deadlines`, `/notifications` | DB outbox, worker; worker/Redis failure retries from DB; delivery failure does not erase alert |
| Dashboards and reports | read projections, aggregate filters, report-export requests | filtered query/export request → projection/export job; `/dashboard`, `/reports` | all read models; no cross-scope aggregation; exports are authorized, watermarked/audited as required |
| AI Scrutiny Copilot | prompt/session metadata, retrieval trace, AI result, feedback | question/document analysis → cited non-binding response; `/copilot/query`, `/copilot/jobs` | catalogue/docs/evidence/OCR; ACL filter before retrieval; offline LLM returns retrieval/manual fallback |
| Audit history | append-only application-level audit events, actor/context, before/after summaries, correlation IDs | all commands → audit timeline; `/audit-events` | all modules; no ordinary update/delete permission; integrity check flags gaps |
| Validation Center and synthetic data | scenario packs, fixture provenance, validation results | seed/run scenario → labelled demo data/report; `/validation/scenarios`, `/runs` | all modules; forbidden in production mode; seed data cannot be marked official |
| Health and diagnostics | health checks, readiness, structured logs, job diagnostics | system probes → health/status; `/health/live`, `/health/ready`, `/diagnostics/jobs` | DB/Redis/storage/AI checks; redact sensitive fields; degraded dependency is explicit |

## Cross-module interaction contracts

- Only the workflow service changes `workflow_instance.current_stage` or records a transition. Specialist modules create prerequisite records and call the transition evaluator.
- A document is referenced by stable `document_id` plus explicit `document_version_id`; a later upload cannot silently alter submitted evidence.
- Requirement version IDs, workflow-template version IDs, policy version IDs, and source-document IDs are copied into records that rely on them.
- A module may read another module's published query/service interface but must not update its tables directly.

## Common failure taxonomy

`401` unauthenticated; `403` insufficient permission/scope; `404` deliberately hidden cross-scope resource; `409` stale version, duplicate idempotency key, or schedule conflict; `422` valid request shape but business prerequisite fails, including a machine-readable `blocking_reasons` array; `429` rate limited; `503` a nonessential dependency is unavailable. State-changing handlers never return success until PostgreSQL commits.
