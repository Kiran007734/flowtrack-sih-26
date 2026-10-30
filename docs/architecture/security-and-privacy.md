# Security and Privacy Architecture

## Security objectives

Protect confidential institution records, prevent unauthorized cross-institution/region access, ensure human accountability for business changes, preserve evidence provenance, and maintain availability during nonessential-service outages. This document is a prototype security design, not a compliance certification.

## Controls by risk

| Risk | Required design control | Verification |
|---|---|---|
| Cross-tenant disclosure | backend RBAC + ABAC scope/relationship checks on every query/command/download; default deny | integration tests with two institutions/regions and ID enumeration attempts |
| Privilege abuse | least-privilege grants, assignment/panel checks, separation of technical admin and decision roles, privileged-action audit | role matrix tests and audit inspection |
| Unauthorized change | CSRF strategy for browser auth, short-lived credentials, idempotency, optimistic concurrency, transaction boundaries | replay, stale write, and CSRF tests |
| Document exposure | private storage adapter, no public directory, ACL content stream/signed private URL, checksums, classification, quarantine/malware-scan integration point | unauthenticated/direct-path and cross-scope download tests |
| Audit tampering | append-only runtime DB grants, event hashes, restricted admin access, integrity verification and retention plan | attempt update/delete under application role; chain verifier |
| Worker/Redis outage | PostgreSQL outbox, durable notification/deadline records, retries/idempotent consumers, scheduler recovery scan | stop Redis/worker then restore and assert one delivery |
| AI data leak/hallucination | pre-retrieval ACL filter, citation requirement, optional local adapter, no action tools, output disclaimer | ACL adversarial queries and unsupported-claim evaluation |
| Injection/supply chain | parameterized SQL/ORM, output encoding, input allowlists, dependency pinning/scanning, secret scanning | SAST/dependency and injection test suite |
| Operational leakage | structured logs with field allowlist/redaction, trace IDs, access controls, error sanitization | log review and forced exception tests |

## Authentication, authorization, and secrets

- Use a standards-based identity adapter. Phase 2 may start with securely hashed local dev accounts, but production requires a confirmed IdP/MFA policy.
- Refresh tokens are stored hashed, rotated, revocable by family, and never logged. Access tokens have short lifetimes and contain a principal ID—not unbounded role/scope data that can become stale.
- Resolve current grants server-side per request or through a short cache with explicit invalidation. Sensitive commands re-check current permissions in the transaction.
- Environment variables point to secrets; `.env` is ignored and example files contain placeholders only. Production secrets belong in an approved secret manager before deployment.

## Data classification, privacy, and retention

Classify fields as public demo, internal operational, confidential institution document, and security-sensitive. Store only necessary personal data. Render/exports apply field-level masking based on role/purpose. Define retention schedules, deletion workflows, legal holds, data-subject handling, data residency, and encrypted-backup policy with the product owner before real data; none are invented in this prototype.

TLS is mandatory between browser and API in deployed environments; encrypt storage and backups using the selected environment's managed controls. Restrict database/network access to service identities. Development data remains synthetic and clearly labelled.

## Audit and incident readiness

Every state change, role/scope change, configuration publish, transition attempt/result, document access/download, export, AI query, and privileged administrative read logs actor, effective scope, action, target, reason when supplied, request/correlation ID, timestamp, and redacted summary. Audit viewers are read-only. Security events are observable through structured logs and health/diagnostics with no raw document content or credentials.

Prepare runbooks for credential compromise, suspected disclosure, malicious upload, failed outbox backlog, failed migration, and AI service failure. Incident notification obligations and escalation contacts are unresolved policy decisions, not assumptions.

## Guidance and mapping controls

Guidance/source metadata is globally readable only to principals with `guidance.read`. Drafting source versions and requirements requires `guidance.manage`; approval, supersession, and archival require `guidance.review`. A version can become `VERIFIED_OFFICIAL` only through the review lifecycle and an approval reason/reference is required for that label. The development seed contains only an explicitly labelled `SYNTHETIC_DEMONSTRATION` source.

Creating a mapping requires `mapping.propose`; confirmation/rejection requires `mapping.review`. The service rechecks application scope and private-document access for the proposing and reviewing principal, validates the supplied immutable document version, and validates optional EVC/compliance evidence against the same document, version, and application. Audit summaries retain identifiers and statuses, never private document contents. Mapping confirmation is a human-reviewed provenance record, not evidence verification, approval, or a workflow command.
