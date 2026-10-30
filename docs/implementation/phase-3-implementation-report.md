# Phase 3 implementation report

## Implemented synthetic scrutiny lifecycle

Revision `0003_scrutiny_lifecycle` adds `scrutiny_reviews`, `scrutiny_findings`, `deficiencies`, and `deficiency_responses`. These records link an application to a human reviewer, structured synthetic requirement reference, assessment, documented deficiency, applicant response, and optional supporting document ID without overwriting prior document versions or findings.

The workflow seed now models `returned` as an exception stage, not a forward path. Only `return_for_correction` can enter it, and that action requires a non-empty reason plus at least one persisted deficiency. `resubmit_after_correction` returns the case to `scrutiny` only after all deficiencies are answered. Both are synthetic demonstration configuration, not official AICTE policy.

## Implemented API contracts

- `POST /api/v1/applications/{id}/scrutiny-reviews` saves a scoped human review/finding during scrutiny.
- `POST /api/v1/applications/{id}/return-for-correction` creates documented deficiencies, transitions atomically, records audit/outbox records, and requires an idempotency key.
- `GET /api/v1/applications/{id}/deficiencies` returns scope-checked deficiency history.
- `POST /api/v1/deficiencies/{id}/responses` records an applicant response under persisted idempotency.

The frontend has a protected real-API scrutiny workspace at `/applications/{id}/scrutiny`; it is visible from an application in scrutiny for permitted reviewer roles.

## Boundaries retained

No official approval/rejection action, official rule/deadline, AI transition, EVC scheduler, undertaking, notification channel, or malware scanner was added. The Phase 2 PostgreSQL audit-privilege release gate remains open.
