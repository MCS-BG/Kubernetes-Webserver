# Compliance Posture

This document states plainly what this platform actually does and does not
provide, so it can't be mistaken for a compliance certification it hasn't
earned. Compliance frameworks (SOX, GAAP, HIPAA, securities regulations)
are legal/audit outcomes, not code -- what follows is the technical
controls this codebase implements in support of those outcomes, and what
is explicitly out of scope until a real client relationship requires it.

## GAAP

The reconciliation and trial-balance engine is built on double-entry
accounting by construction: every check (`app/reconciliation/trial_balance.py`)
verifies that total debits equal total credits and that computed account
activity matches the reported trial balance. This aligns with GAAP's
fundamental accounting equation -- it is not a claim that outputs are
GAAP-compliant financial statements, since that depends on how the client's
own chart of accounts and policies are applied upstream.

## SOX-aligned controls (implemented)

SOX itself is a certification obtained through an external audit, not a
software feature. What's built here, and genuinely testable, is the set of
technical controls SOX-compliant internal controls over financial reporting
typically expect:

- **Immutable audit trail** (`app/security/audit.py`): every source upload,
  reconciliation run, and feedback/approval action is recorded with actor,
  timestamp, entity, and action. The `AuditLog` class has no update or
  delete method -- there is no code path that can rewrite history.
- **Segregation of duties** (`app/api/routes.py` → `/feedback`): the actor
  who approves an exception as a reviewed false positive cannot be the same
  actor who ran the reconciliation it came from. Enforced server-side, not
  just by convention -- see `tests/test_segregation_of_duties.py`.
- **Role-based access control** (`app/security/auth.py`): a minimal
  preparer/reviewer/admin role hierarchy gates the mutating endpoints.
  This is intentionally lightweight (bearer tokens mapped to roles via the
  `AUTH_TOKENS` environment variable) -- a real deployment should sit this
  behind proper SSO/OIDC; the segregation-of-duties logic is what matters,
  and it's provider-agnostic.

**What this is not:** a SOX audit, a claim of SOX compliance, or a
substitute for your auditor's assessment of these controls in context.

## PII

- **Masking before persistence** (`app/security/pii.py`): free-text fields
  are masked (account numbers to their last 4 digits, names to initials)
  before being written to the audit log, so the audit trail itself doesn't
  become a second place PII can leak from.
- The reconciliation engine's own data (bank transactions, GL entries) is
  held in-memory only in this MVP (see README → Roadmap) and is not
  persisted to disk or a third party by this codebase.

**Gap to close before handling real client PII at scale:** encryption at
rest once persistent storage (Postgres) replaces the in-memory store;
a data retention/deletion policy; and a real access-control system in
place of the token-role mapping above.

## HIPAA -- explicitly out of scope

This platform does not implement HIPAA-specific controls (Business
Associate Agreements, PHI-specific access logging, breach notification
procedures) because there is no confirmed client relationship involving
protected health information. Building and claiming HIPAA controls without
a real PHI-handling requirement would be a false compliance claim -- worse
than building nothing, since it would create liability without protecting
anything real.

**If a future client is a healthcare provider and financial data here would
touch PHI:** treat that as a distinct, legal-review-first workstream, not
an incremental code change. Flag it before any such client is onboarded.

## Securities regulations -- explicitly out of scope

No securities-specific controls (SEC/FINRA books-and-records rules for
broker-dealers or investment advisers) are implemented. This platform's
current scope is bank-to-GL reconciliation and close support for
SMB/mid-market operating companies -- not regulated securities entities.

**If the client base expands to public-company issuers, broker-dealers, or
investment advisers:** the specific regime differs by entity type and
needs to be scoped with compliance counsel before any claim is made or
control is built.

## Currency/FX

The FX-mismatch check (`app/reconciliation/flags.py`) compares booked rates
against an independent reference source through a pluggable provider
interface (`app/fx/`) -- this supports audit and control objectives around
accurate currency translation, but is not itself a currency-compliance
certification (e.g. it does not implement OFAC sanctions screening or
similar).

## What to tell a client, verbatim

Use "supports your path toward X readiness" language, never "this makes
you X compliant":

> This platform's reconciliation, audit-trail, and segregation-of-duties
> controls support your organization's path toward SOX-aligned internal
> controls. It does not itself certify compliance with SOX, GAAP, HIPAA,
> or any securities regulation -- that determination belongs to your
> auditors and legal counsel.
