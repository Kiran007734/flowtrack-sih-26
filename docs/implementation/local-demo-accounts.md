# Local demo accounts

These accounts are created only by the development-only seed command after migrations have been applied. They are synthetic, must never be deployed, and are disabled from being seeded when `ENVIRONMENT=production` or `ENABLE_DEVELOPMENT_SEED=false`.

Each account uses the unique local value supplied through `DEVELOPMENT_SEED_PASSWORD`. This value is intentionally not committed, printed by seed commands, or repeated in documentation. Change it only by deliberately resetting your synthetic local data and reseeding.

| Role | Login | Scope | Purpose |
|---|---|---|---|
| Institution Applicant | `applicant.alpha@example.org` | Demo Alpha Institute / Demo North Region | Draft, upload, submit, and own-record isolation demonstration |
| Institution Administrator | `applicant.beta@example.org` | Demo Beta Institute / Demo South Region | Cross-institution denial demonstration |
| Regional Officer | `regional.north@example.org` | Demo North Region only | Regional scope demonstration |
| Regional Officer | `regional.south@example.org` | Demo South Region only | Regional scope demonstration |
| Scrutiny Officer | `scrutiny.north@example.org` | Demo North Region only | Workflow permission demonstration |
| EVC Coordinator | `evc.south@example.org` | Demo South Region only | Synthetic EVC scheduling, evidence and report walkthrough |
| Compliance Officer | `compliance.south@example.org` | Demo South Region only | Synthetic obligation, evidence and validity walkthrough |
| Read-only Auditor | `auditor@example.org` | Synthetic global audit scope | Read-only audit history demonstration |
| System Administrator | `admin@example.org` | Development configuration scope | Development-only configuration and diagnostics |

The seed implementation hashes the configured synthetic password. These credentials are not an identity-provider, MFA, or production-account design.
