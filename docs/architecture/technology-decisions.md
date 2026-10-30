# Technology Decisions

## Decision record

| Area | Chosen approach | Why | Deliberately not chosen |
|---|---|---|---|
| Architecture | Modular monolith with worker processes | One transactional database, simple local operation, clear boundaries for future extraction | Microservices/Kubernetes: premature operational complexity |
| Web client | React, Vite, strict TypeScript, React Router | Fast typed SPA development and explicit feature routing | Server-rendered UI: no stated need |
| UI/data | Tailwind, shadcn/ui, TanStack Query, RHF, Zod, Recharts, Lucide | Accessible reusable primitives, server-state caching, validated forms, charts | Custom component library or client-side global business store |
| API | FastAPI + Pydantic v2 | Typed schemas, OpenAPI, async-friendly request layer | GraphQL: no multi-client aggregation need |
| Persistence | PostgreSQL + SQLAlchemy 2 typed declarative models + Alembic | transactions, constraints, JSONB where needed, durable outbox | Redis/Mongo as primary business store |
| Background work | Celery worker and one Celery Beat scheduler | familiar retryable jobs and one scheduler owner | browser timers/multiple in-process schedulers |
| Cache/coordination | Redis | cache, Celery broker/result coordination, distributed coordination only | storing authoritative deadlines or workflow state in Redis |
| Files | local private filesystem adapter; swappable private object storage adapter | simple development while preserving a production boundary | public static uploads |
| OCR | PaddleOCR | local-capable extraction for supported scans | treating OCR text as verified truth |
| Retrieval | `sentence-transformers/all-MiniLM-L6-v2` embeddings | local semantic retrieval baseline | ungrounded LLM-only answering |
| LLM | optional local Ollama Llama 3.1 8B Instruct | offline-friendly assistance when present | mandatory paid/external AI API |
| Tests | Pytest, Vitest/RTL, Playwright | pyramid from domain to browser tests | only manual testing |
| Local ops | Docker Compose | repeatable API, worker, beat, Postgres, Redis environment | Kubernetes |

## Implementation conventions

- Python 3.12; format/lint/type-check tooling is selected during bootstrap and pinned in lock files.
- SQLAlchemy uses 2.x `Mapped[...]`, `mapped_column`, `relationship`, explicit foreign keys, database constraints, UTC `timestamptz`, and UUID primary keys.
- Alembic is the only schema-change path after the initial migration. Application startup never silently creates production tables.
- REST uses `/api/v1`, JSON, RFC 7807-like problem responses, cursor pagination, and optimistic concurrency (`ETag`/`If-Match` or `version` field) for mutable aggregates.
- Configuration is environment-driven, parsed once by a Pydantic settings object; secrets are never committed.
- A feature flag controls optional LLM calls; OCR and embedding processing are independently switchable.

## Reliability decisions

### PostgreSQL outbox, not Redis durability

Each business transaction writes an `outbox_event` row and any in-app `notification` rows with the business change. A dispatcher periodically scans unprocessed outbox rows with `FOR UPDATE SKIP LOCKED`, sends Celery work when Redis is reachable, and re-scans after outages. Workers make consumers idempotent using the outbox event ID. Notification delivery attempts, provider response, retry time, and terminal status remain in PostgreSQL. Thus a Redis or worker outage delays delivery rather than losing it.

### One controlled scheduler

Only the `scheduler` service runs Celery Beat. Scheduled jobs are idempotent and use Postgres advisory/lease locks before material work. The deadline scan recomputes due work from database records, so a missed tick is recovered on the next successful scan.

### AI degradation

The API serves normal workflows regardless of AI health. OCR job failures retain the source document and show `FAILED` with retry/manual-entry actions. Retrieval can be unavailable while source documents and catalogue browsing remain available. The LLM is optional; when absent, the Copilot returns cited retrieval snippets or a clear unavailable state—never a fabricated answer.

## Decision boundaries to revisit

- Add an enterprise IdP adapter after SSO/MFA requirements are confirmed.
- Add a production object-store adapter, malware scanner, and KMS integration before real confidential material.
- Evaluate a vector index only after corpus size/latency measurements; begin with PostgreSQL metadata plus a local persisted embedding index guarded by document ACL filters.
- Separate services only after measured team, scale, deploy, or fault-isolation needs justify a transaction boundary.
