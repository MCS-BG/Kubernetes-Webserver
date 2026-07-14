# Documentation

Step-by-step guide to the Close & Reconciliation Platform, in the order
you'd actually use it. Each step is a standalone doc with real, runnable
commands -- most of them exercised live against a running instance of this
app while writing this documentation, not invented from reading the code.

| Step | Doc | What it covers |
|---|---|---|
| 1 | [Setup](01-setup.md) | Install, run locally, environment variables |
| 2 | [Entities & Chart of Accounts](02-entities-and-chart-of-accounts.md) | Register a legal entity, classify its GL accounts |
| 3 | [Ingesting Data](03-ingesting-data.md) | CSV/Excel upload, live SaaS/ERP connectors |
| 4 | [Reconciliation](04-reconciliation.md) | Bank-to-GL matching, trial balance tie-out |
| 5 | [Exceptions & Feedback](05-exceptions-and-feedback.md) | Reviewing flags, teaching the system to stop re-flagging known noise |
| 6 | [Currency / FX Checks](06-currency-fx-checks.md) | Detecting booked-rate mismatches against a reference source |
| 7 | [Profit & Loss](07-profit-and-loss.md) | Live P&L via API, chat, or a formula-driven spreadsheet export |
| 8 | [Chat Agent & Web Widget](08-chat-agent-and-widget.md) | Asking for reports by typing or speaking |
| 9 | [Security, Roles & Audit](09-security-roles-audit.md) | Role-based access, segregation of duties, the audit log, PII masking |
| 10 | [Deployment](10-deployment.md) | Running this in production (generic k8s or Azure) |

## Reading this if you're new

Steps 1-4 are the core loop: stand the app up, tell it which entity you're
reporting on, feed it data, reconcile it. Steps 5-7 build on that loop
(exception handling, currency checks, P&L). Step 8 is an alternate way to
do all of the above conversationally instead of via raw HTTP. Steps 9-10
are operational concerns that apply regardless of which features you use.

## Where the source of truth lives

This `docs/` folder is the narrative walkthrough. Three other documents
carry detail this folder deliberately doesn't duplicate:

- **[../README.md](../README.md)** -- architecture overview, directory
  layout, and the fastest path to running the app.
- **[../COMPLIANCE.md](../COMPLIANCE.md)** -- exactly what's implemented
  vs. explicitly out of scope for GAAP/SOX/PII/HIPAA/securities. Read this
  before telling any client anything about compliance.
- **[../AZURE_DEPLOYMENT.md](../AZURE_DEPLOYMENT.md)** -- the full Azure
  deployment runbook (referenced from Step 10, not repeated there).

## Conventions used throughout

- All example commands assume the app is running locally at
  `http://127.0.0.1:8000` (`uvicorn app.main:app`). Swap in your deployed
  URL as needed.
- `<entity_id>`, `<source_id>`, `<reconciliation_id>` are placeholders --
  every step shows where the real value comes from (the JSON response of
  an earlier call), so you can chain them for real rather than guessing.
- Where a doc describes something not yet exercised end-to-end in this
  environment (e.g. a live OAuth flow requiring real credentials), it says
  so explicitly rather than presenting it as verified.
