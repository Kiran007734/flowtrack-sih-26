# API Design

## API conventions

- Base path: `/api/v1`; JSON UTF-8; generated OpenAPI is the contract source.
- Authentication: short-lived access token in a secure transport chosen during Phase 2 and rotating refresh/session family. Browser endpoints use CSRF safeguards if cookies are selected.
- Commands require `Idempotency-Key`; mutable resources return `row_version` and commands send `If-Match` or body version.
- Lists use stable cursor pagination (`limit`, `cursor`) and explicitly documented filter/sort allowlists.
- Dates are ISO 8601 UTC. IDs are UUIDs. File transfer uses multipart upload or controlled resumable flow; content download is separately authorized.
- Errors use `application/problem+json`: `type`, `title`, `status`, `code`, `detail`, `trace_id`, and, when relevant, `blocking_reasons`/field errors. Never expose cross-scope existence in errors.

## Resource catalogue

| Area | Endpoints (representative) | Authorization/audit |
|---|---|---|
| Auth/profile | `POST /auth/login`, `/auth/refresh`, `/auth/logout`; `GET /me` | public rate-limited login; session actions audited |
| Administration | `GET/POST /users`, `/roles`, `/role-grants`, `/institutions`, `/regions` | scoped `user.manage` etc.; every grant/config command audited |
| Applications | `GET/POST /applications`; `GET/PATCH /applications/{id}`; `POST /{id}/submit`; `GET /{id}/timeline` | relationship/scope checks; submit snapshot audited |
| Workflow | `GET/POST /workflow-templates`; `POST /workflow-templates/{id}/versions/{v}/publish`; `GET /applications/{id}/transition-options`; `POST /applications/{id}/transitions/{key}` | configuration or template-defined transition grant; evaluator response is not authority by itself |
| Documents | `POST /documents/uploads`; `POST /documents/{id}/versions`; `GET /documents/{id}`; `GET /documents/{id}/content` | aggregate/doc ACL, upload/download audit; no public content endpoint |
| Scrutiny/deficiency | `GET/POST /scrutiny-cases`; `POST /assignments`; `POST /reviews`; `GET/POST /deficiencies`; `POST /deficiencies/{id}/responses`; `POST /{id}/verify` | assignment and scope checks; return/verify invokes workflow evaluator |
| Requirements/evidence | `GET /requirements`; `POST /requirements`; `POST /evidence-mappings`; `POST /evidence-mappings/{id}/confirm` | catalogue manager or assigned reviewer; source version included |
| EVC/review | `POST /evc-visits`; `POST /evc-visits/{id}/actions/{action}`; `POST /evc-visits/{id}/personnel`, `/checklist`, `/reports`, `/evidence`; `GET /evc-visits/{id}/evidence`; `GET /evc-evidence/{id}`, `/history`; `POST /evc-evidence/{id}/{verify|reject}` | `evc.schedule`, active user, institution/region scope; evidence document and exact version are re-authorized |
| Compliance/validity | `GET/POST /undertakings`; `POST /undertakings/{id}/verify`; `GET/POST /validity-records`; `POST /renewals` | scoped compliance/transition grants |
| Alerts/reports | `GET /deadlines`, `/notifications`; `POST /notifications/{id}/read`; `GET /dashboard`; `POST /exports`; `GET /exports/{id}` | query filters constrained by scope; exports explicit/audited |
| AI | `POST /documents/{id}/ocr`; `GET /ocr-jobs/{id}`; `POST /copilot/query`; `GET /copilot/interactions/{id}` | document/app access rechecked; response is non-binding and cited |
| Audit/ops/demo | `GET /audit-events`; `/health/live`; `/health/ready`; `GET /diagnostics/jobs`; `POST /validation/scenarios/{id}/run` | audit/diagnostic/synthetic-run permissions; production mode forbids demo seed/run |

## Important command contracts

### Transition preview and execute

`GET /applications/{id}/transition-options` returns each presently relevant transition with its role/scope-independent display label plus the caller-specific `allowed` status and reasons. `POST /applications/{id}/transitions/{transition_key}` accepts:

```json
{"row_version": 7, "comment": "Review complete", "acknowledgements": ["uuid"]}
```

Success returns current stage, new `row_version`, history ID and notification summary. A failed prerequisite returns `422` with each machine-readable fact and friendly corrective action. A stale version returns `409`; the request is not partially applied.

### Copilot response

`POST /copilot/query` accepts a question, application context, optional selected documents and mode. It returns `{answer, citations, limitations, model_status, interaction_id}`. Citations contain document/version/passage/line-or-page location that the caller may access. If an LLM is unavailable, `answer` is either a deterministic retrieved-evidence summary or null with an actionable availability message; it never guesses.

## Endpoint design safeguards

- Bulk commands require explicit selection IDs, count limits, preview, permission checks per resource, and per-record audit results.
- Export is asynchronous: `POST /exports` creates a database request; a worker creates an encrypted/controlled artifact, records checksum/expiry, and only the authorized requester can download it.
- OpenAPI request/response schemas are generated from Pydantic v2 and copied into frontend types through a deliberate client-generation step or maintained contract package.
- No endpoint accepts an arbitrary role, institution, stage, or user ID as proof of access; those are validated against the authenticated principal.
