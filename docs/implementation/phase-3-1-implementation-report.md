# Phase 3.1 implementation report

## Assignment-aware scrutiny authorization

Migration `0004_reviewer_assignments` adds persisted application-specific assignments with reviewer, assigning actor, `SCRUTINY` responsibility, `ACTIVE|REVOKED` status, validity window, revocation time, and reason. Assignment records are retained; revocation never deletes prior authorization history.

Only an in-scope regional officer with `scrutiny.assign` can create/revoke assignments. The selected reviewer must be active, possess `scrutiny.review`, and have institution/region scope for the case. Reviewer actions now require active role/scope **and** a currently valid `SCRUTINY` assignment. Revocation immediately prevents new review/return actions.

## Complete implemented user journey

- Regional officer routes a submitted synthetic case to scrutiny and assigns an eligible reviewer.
- Assigned reviewer saves structured findings and can return the case only with a reason and one or more deficiencies.
- Applicant sees deficiencies, records correction responses, uploads new private document versions through the existing uploader, and can resubmit only after every deficiency is answered.
- The case returns to scrutiny through the configured synthetic transition; findings, documents, responses, audit events, stage history, and outbox events remain retained.

The React application now includes a real-API correction package panel and an authorized assignment/history panel on application detail. The assignment panel takes an existing reviewer UUID because a general user-directory endpoint was not in the approved Phase 3.1 scope; backend eligibility remains authoritative.

## Remaining boundaries

No statutory decision, official AICTE policy, deadline, EVC, undertaking, AI action, email/SMS integration, or reviewer-directory feature is claimed. The PostgreSQL audit-table privilege gate remains open until run against real PostgreSQL.
