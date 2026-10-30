# Phase 2 implementation decisions

## Scope implemented in this phase

Phase 2 implements the FlowTrack foundation described in `docs/architecture/`: a modular FastAPI application, React/Vite browser client, PostgreSQL-backed models and migrations, Redis/Celery coordination, local development authentication, scoped authorization, audit/outbox records, private local document storage, synthetic seed data, and the initial application submission workflow.

The following boundaries remain intentionally out of scope: OCR, embeddings/retrieval, LLM/Copilot integration, EVC scheduling policy, undertakings, full expiry/escalation rules, executive reporting, official AICTE integration, and any official statutory determination.

## Decisions and defaults

| Decision | Prototype default | Why |
|---|---|---|
| Runtime architecture | Modular monolith plus separate Celery worker and singleton scheduler | Preserves a single PostgreSQL transaction boundary while retaining clean module seams. |
| Authoritative data | PostgreSQL only | Redis is used only for cache/broker/result coordination; it is never the source of an application state, audit event, or notification. |
| Local authentication | Argon2-hashed local accounts and short-lived signed bearer access tokens | No approved institutional identity provider was provided. The auth service is kept behind a replaceable boundary. |
| Password library | `pwdlib[argon2]` | The initially evaluated Passlib/bcrypt combination failed against the host bcrypt backend during real tests. Argon2 through pwdlib is maintained, passed the suite, and avoids that compatibility defect. |
| Refresh-token rotation | Deferred | Phase 2 binds short-lived access tokens to a server-side revocable session and supports logout. Rotating refresh-token families require an agreed browser/session transport before institutional deployment. |
| MFA/SSO | Deferred | An approved identity provider, MFA policy, issuer, audience, and operational owner are required before institutional use. |
| Workflow rules | Versioned synthetic configurations labelled `SYNTHETIC_CONFIGURATION` | No verified official AICTE handbook/rule source was supplied. |
| Notification channels | Durable in-app notifications only | No sanctioned email/SMS provider or recipient policy is configured. |
| File storage | Private local volume adapter | Appropriate for local development; an object-storage adapter is a defined future extension, not faked. |
| Encryption/KMS and retention | Configuration placeholders only | Key-management, retention, residency, legal-hold, and backup policy need product-owner and institutional decisions. No compliance claim is made. |
| Malware scanning | Not implemented | No scanning service is configured. Type/size/path validation is implemented, but real confidential-file deployment requires a scanner. |
| EVC scheduling | Extension point only | Calendar policy, delegation rules, and constraints are unresolved. |
| Command idempotency | Persist command request hash and response by actor/operation/key | Header validation alone did not make retries safe. Revision `0002_command_idempotency` replays identical application/document/notification commands and rejects altered reuse. |
| Initial migration scope | Frozen Phase 2 table-name set | The original metadata-driven initial migration could absorb a future ORM model. Its table set is now fixed; future schema work requires an explicit revision. |

## Architecture consistency review

No conflict was found between the Phase 1 architecture and the Phase 2 foundation scope. The implementation retains the key Phase 1 constraints: backend-enforced record scope, a human-only workflow transition executor, immutable-style audit history, stable document versions, and PostgreSQL-backed outbox processing.

## Environment limitation observed during implementation

The development host has Node 24.14.1 and no available `docker` command. Python 3.12.13 was installed through `uv` for host-side linting, migration mechanics, and API tests. Docker Compose build/start, real PostgreSQL-backed integration tests, Celery/Redis execution, and persistence validation remain unverified until run on a Docker-capable host.

The strict Phase 2.1 audit also identified a release gate: PostgreSQL runtime grants must be validated and tightened so the application account cannot update or delete `audit_events`. The host cannot verify that PostgreSQL-specific privilege boundary without Docker or a supplied PostgreSQL test database.

## Deferred decisions

| Deferred item | Why it is deferred | Safe current behavior |
|---|---|---|
| Approved IdP and MFA | Credentials and security policy are absent | local-only auth; no production defaults/accounts |
| Official sources and dates | No verified source corpus provided | only synthetic route data; no official deadline/requirement claims |
| Email/SMS configuration | No provider/account or recipient policy | in-app outbox notification only |
| KMS, storage encryption, retention | Governance and platform choices pending | private local storage, configuration hooks, no compliance assertion |
| EVC policy | Product process not specified | no scheduling feature or fabricated constraint |
