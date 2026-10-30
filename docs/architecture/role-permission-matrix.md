# Role and Permission Matrix

## Authorization model

The backend evaluates `permission + scope + relationship + record state`. A role is a set of permissions; a grant is limited to one or more institutions, regions, assignments, review panels, or global administration. A role alone is insufficient. Scoped queries filter at the database/service layer before serialization. Cross-scope records return `404` where disclosure itself is inappropriate.

| Role | Default scope | May view/create/update | May assign/verify/return/schedule/close/export | Explicit prohibitions |
|---|---|---|---|---|
| Institution Applicant / Administrator | own institution(s) only | create/edit own drafts, upload/version own documents, submit, respond to deficiencies, submit undertaking evidence | may request permitted export of own records; cannot assign/verify/return/schedule/close officer work | no other institution, no internal assignment/review, no official status override |
| Scrutiny Officer | explicitly assigned applications | view assigned case/evidence; create review records, findings and deficiencies | may verify evidence within assignment and recommend/return through allowed workflow transition; export assigned case | no unassigned records, template/admin changes, final statutory action |
| Regional Officer / Administrator | explicitly granted region(s), not all regions by default | view/manage in-scope cases and regional assignments | may assign/reassign, validate configured transitions, manage EVC queue, export regional reports | no other region without grant; cannot bypass workflow/required review |
| EVC Member | assigned visits only | view visit pack; create individual visit observations | may submit assigned observation; export visit pack if policy permits | no schedule changes, no unrelated application access, no outcome closure alone |
| EVC Coordinator | explicitly granted region(s)/visits | manage in-scope EVC queue, availability and visits | schedule/reassign/cancel within policy; compile outcome; export in-scope schedules | no unsupported final decision, no other region by default |
| SAC/SHC Committee Member / Authorized Reviewer | assigned panel/stage only | view assigned stage pack; create recommendation/deliberation record | may submit review/recommendation, export assigned pack if allowed | no route/template changes or official finalization unless separately granted |
| Compliance Officer | explicitly assigned institutions/regions or global compliance grant | view compliance/undertaking/validity records, create observations | may verify compliance evidence, issue/close undertaking where workflow allows, export scope | no approval/rejection, no unscoped data access |
| System Administrator | global technical administration, not implicit business decision authority | manage users/roles/scopes, templates, catalogue configuration, diagnostics | may configure, deactivate, seed synthetic data, export admin audit/config reports | all operational changes audited; cannot impersonate, silently alter audit history, or infer officer decision rights unless separately granted |
| Read-only Auditor | explicitly granted audit scope | view immutable history, records, reports and approved exports | may export authorized audit report | no create/update/assign/verify/return/schedule/close; no download confidential files unless explicit document-read grant |

## Permission catalogue

| Permission family | Examples | Primary holders |
|---|---|---|
| `application.read/write/submit` | draft edit, submit, read submitted snapshot | applicant (own), officers (scope) |
| `workflow.transition` | request named transition after engine evaluation | authorized role per template |
| `scrutiny.assign/review/deficiency.manage` | assign, record finding, raise/verify/close deficiency | regional admin, scrutiny officer by assignment |
| `document.read/write/download` | metadata/content/version upload | relationship- and scope-based |
| `evc.schedule/observe/outcome.manage` | create visit, submit observation, compile outcome | coordinator/member as appropriate |
| `review.record` | committee stage recommendation | panel-assigned reviewer |
| `undertaking.manage/verify` | issue, respond, verify/close | compliance/officer per template |
| `catalogue.manage/workflow-template.manage` | create/publish versioned config | system administrator with configuration grant |
| `guidance.read/manage/review` | read catalogue; draft source/requirements; approve/archive governed guidance | readers; constrained administrators; independent guidance reviewer |
| `mapping.propose/review` | propose exact-version relationship; human confirm/reject it | scoped applicants/officers; scoped authorized reviewers |
| `report.export/audit.read` | request export/read audit | scope-specific officer/auditor |
| `user.manage/role.grant` | user and scope administration | constrained system admin |

## Enforcement rules

1. Routes use an `authorize(action, resource, principal)` dependency/service; direct ORM lookups are not exposed to handlers.
2. Assignment-bound roles additionally require an active matching assignment or panel membership at command time.
3. Transition permissions are intersected with the role list embedded in the selected workflow-template version.
4. Download checks document ACL, source aggregate access, retention/quarantine status, and purpose; it writes a `DOCUMENT_DOWNLOADED` audit event.
5. Administrator configuration changes use maker/checker review when policy requires it; this prototype records the need even if the policy is not yet supplied.
6. Audit event creation is mandatory for privileged reads, exports, all commands, denied high-risk actions, and configuration publication.

## Phase 3 implemented subset

`scrutiny.review` and `deficiency.manage` are seeded only for synthetic scrutiny/regional officer roles. The backend also requires institution/region scope, the scrutiny stage, and a valid active `SCRUTINY` reviewer assignment. `scrutiny.assign` is held by the synthetic regional-officer assignment authority. Assignment creation validates reviewer activity, role permission, and case scope; revocation takes effect for later review commands.
