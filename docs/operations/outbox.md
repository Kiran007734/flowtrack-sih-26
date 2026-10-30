# Transactional outbox operations

## Guarantee

For a critical command such as application submission, the API commits the application mutation, stage history, audit event, and `outbox_event` in the same PostgreSQL transaction. Redis and Celery are not required for that commit. A Redis or worker outage therefore delays background notification creation; it does not discard the durable pending event.

Phase 2 supports the `APPLICATION_SUBMITTED` event type. Its idempotent consumer creates an in-app notification and then records the outbox result. It does **not** claim an email or SMS was delivered.

## Processing lifecycle

1. A command writes an unprocessed outbox event with an idempotency key.
2. A worker/dispatcher finds eligible events, claims one with a lease/row lock, and commits that claim before external or slow work.
3. The consumer processes the supported event in a short transaction.
4. On success it writes/updates the idempotent notification and `processed_at`.
5. On a transient failure it records a safe error summary, increments attempts, and sets `next_attempt_at` using bounded backoff.
6. At the configured attempt limit it records a terminal failure for operator investigation; the source business record remains valid.

Consumers must derive a notification key from the event ID/type or supplied idempotency key and enforce it with a database uniqueness constraint. Retried Celery messages and concurrent workers may therefore cause at-least-once processing attempts but not duplicate logical notifications.

## Recovery runbook

1. Check API/worker/scheduler logs and `GET /health/ready`; do not manually update application or workflow tables.
2. Restore the failed dependency (for example Redis or the worker process).
3. Inspect pending/claimed/failed outbox rows with authorized diagnostics or the database support procedure. Check oldest `available_at`/`next_attempt_at`, attempt count, and safe error summary.
4. Allow the dispatcher to replay eligible rows. If an operator must retry a terminal event, use a future privileged, audited retry command—not a direct status edit.
5. Confirm a matching in-app notification and audit correlation exist once, then confirm `processed_at` is set.
6. Record incident timing and recovery result. The outbox row and audit trail remain evidence of the event.

## Validation expectations

Run the backend outbox tests plus a Docker-backed fault exercise when Docker is available: submit an application while workers are stopped, start a worker, run/trigger dispatch, and verify exactly one in-app notification. Then repeat dispatch to prove idempotency. This host did not have Docker available at the time Phase 2 infrastructure was authored; see the phase test report for actual executed results.

## Boundaries

The outbox is not an official deadline engine and does not itself decide workflow state. It carries safe identifiers/metadata rather than confidential document bytes, passwords, bearer tokens, or raw file content.
