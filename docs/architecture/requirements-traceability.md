# Requirements Traceability

## Classification

`M` = mandatory prototype function from the brief. `E` = prototype enhancement that improves demonstration/operability. `F` = future scope requiring policy, integration, or scale validation. “Screen” names describe Phase 2 targets; they are not implemented in Phase 1.

| ID | Class | Requirement | Responsible module/data | API and Phase 2 screen | Job | Verification test |
|---|---|---|---|---|---|---|
| R-01 | M | Authorized human approval workflow support | Applications, Workflow; application/version, template/instance/history | `/applications`, `/transitions`; Application detail/Workflow timeline | deadline creation | T-04 human transition audit; T-08 template validation |
| R-02 | M | Institution application creation/submission | Applications; drafts/submitted snapshots | `/applications`, `/{id}/submit`; Applicant workspace | none | T-01 tenant isolation; T-03 submission immutability |
| R-03 | M | Role-based authorized access | IAM plus Phase 3.1 reviewer assignments, institution/region/assignment scopes | `/me`, reviewer assignments; Role admin/Access denied | cache invalidation optional | T-01/T-02 cross-scope plus assignment revocation regression |
| R-04 | M | Scrutiny assignments/reviews | Reviewer-owned reviews/findings plus persisted active/revoked assignment scope | `/applications/{id}/scrutiny-reviews`, reviewer assignments; Scrutiny workspace | assignment reminder deferred | Scoped review and assignment-revocation regression |
| R-05 | M | Deficiency return/correction/resubmission | Phase 3 subset: deficiency/response/history | `/return-for-correction`, `/deficiencies/{id}/responses`; Deficiency response | overdue scan deferred | T-06 evidence-preserving return/resubmit regression |
| R-06 | M | Versioned document handling/access | Documents; asset/version/ACL/hash | `/documents`; Document vault/viewer | scan/OCR | T-07 private/versioned download |
| R-07 | M | EVC coordination/scheduling/outcomes | Synthetic visit, checklist/report lifecycle, exact-version evidence, scoped dashboard/detail APIs, configured prerequisites, durable in-app reminder outbox/audit | `/evc-visits`, lifecycle, checklist, report, evidence, reminder APIs; React EVC workspace | Celery beat queues synthetic reminders; no production delivery claim | EVC/evidence/workflow regression plus reminder dedup/delivery/suppression unit test; PostgreSQL conflict test blocked |
| R-08 | M | SAC/SHC/configurable review stages | Workflow, Configurable review; stage/panel records | `/panel-reviews`; Review-stage workbench | stage due reminder | T-10 panel assignment only |
| R-09 | M | Undertakings/evidence/verification | Synthetic compliance obligation/evidence persistence, exact document-version reference, human return/verify/reject lifecycle, audit/outbox | `/compliance-obligations`, `/compliance-evidence`; Compliance workspace | synthetic due/evidence scanner | Compliance lifecycle scope/version/reason/verification regression; workflow prerequisite integration remains future |
| R-10 | M | Document validity/expiry/renewal | Validity record with category, authority, optional issue/expiry, exact version, renewal/verification status | `/validity-records`, `/validity-records/{id}/renew`; Compliance workspace register | synthetic advance-expiry scanner | Validity date/version regression; Redis/Celery runtime blocked |
| R-11 | M | Deadline alerts/escalations | EVC synthetic reminder scanner, outbox, in-app notification adapter and audit events | `/notifications`, `/evc-visits/{id}/reminders`; EVC workspace | Celery beat scans synthetic configurable lead/overdue windows | Reminder dedup/delivery/suppression/overdue-retry unit tests; Redis/Celery runtime blocked |
| R-12 | M | Dashboard/report aggregates | Scoped pendency aggregation from persisted applications, history, assignments, EVC, compliance and validity records | `/dashboard/pendency`; Pendency dashboard and case drill-down | query-time synthetic deadline/ageing evaluation | Scoped dashboard total/stage/drill-down regression; exports remain future |
| R-13 | M | Immutable-style audit records | Hash-chain audit events; PostgreSQL runtime-role protection migration `0008` revokes update/delete | `/audit-events`; Audit timeline | integrity verifier | Audit presence tests; PostgreSQL privilege contract exists but is blocked pending real runtime DB |
| R-14 | M | AI OCR/extraction | Private, version-pinned guidance ingestion runs/pages with embedded-PDF extraction and image OCR adapter; raw text, warnings, correction audit, review gate and Celery/synchronous execution boundary | `/guidance-versions/{id}/ingestions`, `/guidance-extraction-runs`; Guidance catalogue | durable queued run plus optional Celery worker; explicit synchronous development fallback | Ingestion pinning/audit/review regression; host OCR-engine and broker runtime remain unverified |
| R-15 | M | Requirement/evidence mapping | Versioned guidance source/requirement catalogue and human-reviewed exact-document-version mappings; no passages/OCR/semantic suggestions | `/guidance-sources`, `/catalogue-requirements`, `/requirement-evidence-mappings`; Guidance catalogue | none | Source lifecycle, exact-version mapping, scope, review/supersession regression; approved corpus citations remain future |
| R-16 | M | Grounded AI Copilot | ACL-scoped deterministic metadata fallback plus governed source/mapping substrate; no OCR/embedding/LLM/copilot ledger | `/applications/{id}/ai-scrutiny-assist`; Guidance catalogue | none | Scoped non-binding fallback and catalogue lifecycle regression; genuine Copilot remains future |
| R-17 | M | Synthetic demonstration/validation | Idempotent development seed plus SIH runbook | `docs/operations/sih-demo.md`; synthetic role walkthrough | seed command | Seed guards and documented synthetic walkthrough; Validation Center remains future |
| R-18 | M | Health/logging/diagnostics | Operations; health/job status/structured logs | `/health/*`, `/diagnostics/jobs`; Admin diagnostics | health probes | T-20 degraded dependency reporting |
| R-19 | M | Versioned data-driven route configurations | Workflow; template version/stage/transition/policy source | `/workflow-templates`; Route template admin | policy publish checks | T-08 graph/source checks |
| R-20 | M | No automatic AI/state authority | Copilot/Workflow/Audit; action provenance | no AI command route; UI disclosure | none | T-18 action denial and audit tests |
| R-21 | E | Accessibility/usability | Web UI; semantic components/form errors | all UI routes; keyboard/screen-reader states | none | T-21 RTL/Playwright accessibility smoke |
| R-22 | E | Controlled async exports | Reporting/Audit; export request/artifact/access log | `/exports`; Export status | export worker | T-14 scope/expiry/download audit |
| R-23 | F | Verified official rule catalogue | Catalogue/source governance; verified sources/sign-off | source publication UI | re-index | T-22 source sign-off workflow |
| R-24 | F | Official AICTE/identity/channel integrations | adapter boundaries/config | adapter-specific APIs/screens | sync/channel jobs | T-23 contract/security tests |
| R-25 | F | Production retention/residency/KMS | security/deployment policy records/config | admin policy screens | archival/purge jobs | T-24 retention/restore drills |

## Test case shorthand

T-01 through T-20 are the critical scenarios in `testing-strategy.md`, expanded into named automated test cases during Phase 2. T-21 through T-24 are future/enhancement acceptance suites and are not claimed as built.

## Requirement source handling

The problem-statement capabilities above are the sole mandatory input at this stage. Any apparent deadline, route, document type, determination standard, handbook passage, or escalation recipient must enter as `SYNTHETIC_CONFIGURATION` until its source document, version, applicable passage, verifier, and verification date are captured. This preserves demo realism without pretending legal or official authority.

## Step 3 secure ingestion status

Guidance extraction is deliberately separate from AI retrieval. It accepts an authorized private PDF, PNG or JPEG document version, records its immutable checksum and extractor configuration, and exposes text only to callers who retain access to that underlying document. Embedded PDF text uses `pypdf`; images use the locally configured Tesseract adapter through `pytesseract`. Low-text output is marked for human review rather than treated as OCR success. An approved extraction remains a review aid, not an official rule or an automated workflow decision. The current environment has not verified a Tesseract executable, Redis/Celery worker or PostgreSQL migration/audit privilege contract.
