# Phase 4 implementation report

## Implemented EVC foundation

Migration `0005_evc_visits` adds a synthetic EVC visit bound one-to-one to an application, with institution/region/coordinator scope, scheduled timestamp/timezone/duration, optimistic row version, personnel/checklist/report persistence extension points, and a durable audit/outbox lifecycle.

The implemented visit state path is `PROPOSED -> CONFIRMED -> IN_PROGRESS -> COMPLETED`, plus `PROPOSED -> CANCELLED` with a reason. It is a configurable synthetic baseline, not a claim about official AICTE visit policy. Creation requires an application currently at its configured `evc` stage, a future timezone-aware start, and an in-scope `evc.schedule` coordinator. One visit per application is enforced.

`POST /api/v1/evc-visits` and `POST /api/v1/evc-visits/{id}/actions/{confirm|start|complete|cancel}` use persisted idempotency, row versions, audit events, and outbox events. Redis is not authoritative and no external message delivery is claimed.

Phase 4.1 activates the existing persistence seams with scoped idempotent commands for personnel assignment, synthetic checklist-item creation, and report submission. Personnel eligibility checks active account, existing application-read permission, and institution/region scope; availability is not modelled or claimed. Report submission requires a completed visit and emits a durable outbox event. These records remain separate from statutory application approval.

Phase 4.2 adds checklist completion provenance and secured report lifecycle actions: `SUBMITTED -> RETURNED -> SUBMITTED -> ACCEPTED -> CLOSED`. A return requires a reason; every action is idempotent, audited, and creates a durable outbox event. The visit action route is explicitly namespaced as `/evc-visits/{id}/actions/{action}` so it cannot intercept checklist/report resource routes.

## Tested scope

The synthetic EVC regression proves a South-region EVC coordinator can propose a visit idempotently, a North officer cannot schedule that case, and the configured confirm/start/complete sequence succeeds. It does not prove PostgreSQL locking, worker delivery, or live calendar availability.

## Phase 4.3 evidence integrity and configured prerequisites

The persisted `evc_evidence_links` model is now active through scoped APIs: `POST` and `GET /api/v1/evc-visits/{visit_id}/evidence`, `GET /api/v1/evc-evidence/{link_id}`, `POST /api/v1/evc-evidence/{link_id}/{verify|reject}`, and `GET /api/v1/evc-evidence/{link_id}/history`. Responses expose evidence metadata only; private storage keys and URLs are never returned.

Evidence linking re-authorizes the supplied private document, requires it to belong to the visit application, and verifies that the supplied document version belongs to that document. Links retain the exact version ID and are never retargeted on later uploads. Linking and verification/rejection have persisted command idempotency, audit events, and durable outbox records. Rejection requires a reason. Access is limited to a live `evc.schedule` coordinator with institution/region scope. There is no separately configured EVC evidence-review role in this synthetic seed, so the existing coordinator permission governs verification; this must be revisited before a separation-of-duties policy is claimed.

The workflow evaluator recognizes explicitly configured synthetic facts only: `evc.visit.completed`, `evc.report.accepted`, `evc.checklist.completed` (optionally `labels`), `evc.evidence.linked` and `evc.evidence.verified` (optionally `purposes`), and `evc.human_review.completed`. These facts merely block or allow a separately configured, permission-controlled transition. They do not approve an application and are not present in the default seeded workflow, so no approval rule was silently changed.

## EVC completion sprint

The scheduler now queues durable, in-app synthetic reminders every five minutes through Celery beat. `EVC_REMINDER` outbox events use an idempotency key comprising visit, reminder kind and the visit's local calendar day. The scanner honors configured `EVC_REMINDER_LEAD_HOURS` and `EVC_REMINDER_OVERDUE_HOURS`; it covers upcoming confirmed visits, outstanding checklist items, missing reports after completed visits, submitted reports awaiting review, returned reports awaiting correction, and overdue confirmed/in-progress visits. Cancelled visits do not generate new reminders. Outbox delivery creates in-app notifications and records queued, delivered, and failed delivery audit events. This is a deterministic development/test adapter, not email delivery.

The React EVC workspace adds real API-backed overview, visit list, and visit-detail routes. It provides lifecycle actions, checklist completion, evidence verification/rejection, report submission/review, reminders, loading/empty/error states, and query invalidation. The backend additionally supplies scoped visit listing, visit detail, and reminder-event APIs. The UI is limited to users shown the EVC workspace navigation; server-side `evc.schedule` and institution/region authorization remain authoritative.

Migration investigation confirms that `0006_evc_evidence_and_report_lifecycle` calls `op.create_foreign_key` after `op.add_column`. PostgreSQL supports that operation and remains the authoritative target. Alembic's SQLite implementation raises `NotImplementedError` for it because SQLite needs batch/table-rebuild migration operations. The historical migration was not rewritten. No additive SQLite compatibility migration was added because it cannot make a fresh upgrade pass before `0006`; SQLite migration support is therefore not currently a project guarantee. The PostgreSQL audit-table privilege release gate remains open pending a real PostgreSQL run.

## Deferred Phase 4 scope

No browser E2E suite, production PostgreSQL/Celery/Redis run, configurable checklist mandatory flag, or dedicated reviewer separation-of-duties role is implemented. The UI does not yet create personnel, checklist, or evidence links; those existing secured APIs remain available. The existing outbox safely records EVC events, but no email or external delivery is claimed.

## Compliance and document validity sprint

Migration `0007_compliance_validity` adds synthetic compliance obligations, immutable document-version evidence submissions, and document validity records. The secured lifecycle supports obligation creation, evidence submission, return with a mandatory reason, verification or rejection by a `compliance.verify` human, and validity registration/renewal. Dates are optional for documents with no configured expiry; if both are supplied, expiry must be later than issue. Validity records retain an exact private document-version reference and never expose storage paths.

The existing scheduled reminder worker now also queues deterministic in-app reminders for due/overdue obligations, missing or submitted evidence, returned corrections, documents approaching expiry, and expired documents. A daily synthetic key prevents duplicates, and closed/verified obligations and renewed documents are suppressed. These deadlines are configurable synthetic data, not official AICTE timelines.

The React Compliance workspace is backed by live obligation and validity APIs and presents real outstanding/review/expiry counts, scoped records, loading, error/retry and empty states. It now includes obligation creation, exact-version evidence submission, review actions, validity registration, renewal, and obligation audit lifecycle; the browser never receives private storage paths.

## Pendency intelligence and dashboard sprint

`GET /api/v1/dashboard/pendency` derives role-scoped KPI totals and drill-down cases from persisted applications, workflow-stage history, active reviewer assignments, EVC visits, compliance obligations and validity records. Ageing is explicitly days since the most recent stage-history action (or record update); overdue means an open synthetic compliance obligation with a configured due timestamp before the dashboard timestamp. Counts are calculated after institution/region scope filters; scrutiny-only reviewers are additionally restricted to their active assignments. All deadline indicators remain synthetic configuration.

The React Pendency Dashboard consumes this endpoint directly and provides KPI cards, stage and ageing breakdowns, scoped case drill-down links, real data timestamp, and loading/error/empty states. The first operational dashboard intentionally does not infer productivity improvements or statutory timelines.

## Final feature-completion sprint

The Compliance workspace now calls the existing secured obligation, evidence-review, validity-registration and renewal APIs. It supports obligation creation, exact-version evidence submission, human verify/return/reject actions, validity registration and renewal; mutations invalidate live records and surface API errors without clearing entered form data. Obligation detail includes persisted audit lifecycle and a scoped reminder-history API. Document IDs and exact version IDs are entered from authorized records; private storage paths remain unavailable to the browser.

`GET /applications/{id}/ai-scrutiny-assist` provides a read-only, ACL-scoped deterministic fallback. It reports accessible submitted document-version metadata, persisted compliance evidence status, open synthetic obligations, and human-review suggestions. It explicitly declares that no approved guidance corpus, OCR extraction, embeddings or LLM response is available, so it returns no invented requirement citations, page references or legal conclusions. It cannot mutate state, verify evidence, or advance workflow; the application detail screen labels it non-binding.

Browser E2E journeys were not added because Playwright is not a project dependency and browser/runtime services are unavailable. PostgreSQL audit privilege, PostgreSQL migration, Redis/Celery live delivery and Docker remain release gates rather than completed checks.

## System acceptance and SIH readiness

The acceptance audit found and corrected a deployment security defect: the Docker application role inherited `UPDATE` and `DELETE` on `audit_events` from its general default table grants. Additive PostgreSQL-only migration `0008_protect_audit_events` now revokes those rights while retaining `INSERT` and `SELECT` for the runtime role. The real PostgreSQL contract test now checks these grants when `TEST_POSTGRES_DATABASE_URL` is supplied. It is still a release gate until it passes against the actual runtime role and migrated database.

The SIH runbook is in `docs/operations/sih-demo.md`. It uses only idempotent, clearly synthetic seed data and specifies both the demonstration sequence and unsupported claims that presenters must avoid.

The Phase 2 PostgreSQL audit-table privilege gate remains unresolved.

## Grounded guidance and requirement catalogue milestone

Additive migration `0009_guidance_catalogue` introduces a governed, metadata-first foundation for grounded compliance intelligence. `guidance_sources` provides a stable source identity; `guidance_source_versions` retains version label, optional effective date/content hash/upload metadata, verification label and review provenance. Its lifecycle is `DRAFT -> SUBMITTED -> APPROVED`, with authorized supersede/archive paths. Approved versions have no update route; changes require a new version. An entered URL, upload reference, or `OFFICIAL_REFERENCE` source type does not establish official status. Approval of a `VERIFIED_OFFICIAL` version requires a reviewer-supplied reason/reference. The repeatable development seed adds one prominently labelled synthetic demonstration source only.

`catalogue_requirements` versions a stable identifier against an exact guidance source version with category, module, section reference, applicability/evidence metadata and provenance. Requirements must be submitted and approved after their referenced guidance version is approved. A newer requirement can supersede an older requirement version without changing any historic mapping.

`requirement_evidence_mappings` pins a requirement version to an application, private document, and exact private document version. Optional EVC/compliance references are accepted only if they point to the same document/version and the same application. Proposals are `MANUAL_REVIEW` and start `PROPOSED`; only `mapping.review` can confirm/reject them, rejection requires a reason, and a confirmed replacement supersedes the earlier reviewed mapping without overwriting it. A mapping never verifies evidence, satisfies a requirement, or changes application/EVC/compliance workflow state.

The secured API surface is `/guidance-sources`, `/guidance-sources/{id}/versions`, `/guidance-versions/{id}/{submit|approve|supersede|archive}`, `/catalogue-requirements`, `/catalogue-requirements/{id}/{submit|approve|archive}`, and `/requirement-evidence-mappings` with review actions, individual mapping lookup, and scoped mapping audit history. New least-privilege permissions are `guidance.read`, `guidance.manage`, `guidance.review`, `mapping.propose`, and `mapping.review`; all commands use the existing idempotency, transaction and audit patterns.

The React `/guidance` workspace has live source/version badges, catalogue search, draft source/requirement forms, lifecycle controls, mapping proposal/review controls, scoped mapping audit-history display, loading/error/retry/empty states, mutation feedback and query invalidation. It never displays document contents or storage keys. It deliberately does not implement OCR, full-text ingestion, passages/page citations, embeddings, vector retrieval, or an LLM.
