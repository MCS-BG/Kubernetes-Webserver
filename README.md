# Close & Reconciliation Platform

Automated bank-to-GL reconciliation and trial-balance tie-out for Two
Rivers Advisory. Ingests a bank feed, a general ledger, and a reported
trial balance (via live SaaS/ERP API or a CSV/Excel export), matches
transactions across them, and flags exactly which line items don't
reconcile and why -- so a close that took days of manual matching takes
minutes of reviewing exceptions instead.

**New here?** [`docs/`](docs/README.md) walks through every step end to
end -- setup, entities, ingestion, reconciliation, exceptions, FX, P&L,
chat, security, and deployment -- with real commands and real output from
this repo's own sample data. This README stays the high-level tour; the
docs folder is the hands-on runbook.

## What it does

1. **Ingests** bank + GL + trial balance data, either from a one-time
   CSV/Excel export (ERP data migration) or a live-connected SaaS finance
   app.
2. **Matches** bank transactions to GL entries in increasingly permissive
   passes (exact, date-window, fuzzy description), so only genuine
   exceptions are left over.
3. **Ties out** the trial balance: does the GL activity we computed match
   what the ERP reports per account, and does the ledger balance at all
   (total debits == total credits)?
4. **Flags** currency mismatches: for multi-currency entries, is the FX
   rate that was actually booked consistent with an independent reference
   rate (OANDA, ECB/Frankfurter, or whichever provider is configured)?
5. **Surfaces** every exception through a small HTTP API and a headless
   chat agent -- ask "run the June close for Acme Ops LLC" by typing or
   speaking, no dashboard required.
6. **Learns from review**: when a human marks an exception as a known
   false positive, that decision is recorded and suppresses the same
   recognized noise on future runs for that entity.
7. **Reports a live profit & loss**: revenue, COGS, gross profit, itemized
   operating expenses, operating income, other income/expense, and net
   income -- computed fresh from GL activity for any date range, via API,
   chat, or a downloadable spreadsheet with real formulas throughout.

## Architecture

```
app/
  models.py            Core domain types: BankTransaction, GLEntry,
                        TrialBalanceLine, Flag, ReconciliationResult
  config.py             Settings (tolerances, FX provider choice)
  ingestion/            One adapter per data source, all implementing
                        SourceAdapter (fetch_bank_transactions,
                        fetch_gl_entries, fetch_trial_balance)
    csv_excel.py          Generic CSV/Excel importer (ERP data migrations)
    quickbooks.py         QuickBooks Online: OAuth 2.0 + Accounting API
    netsuite.py           Interface defined; live sync on client demand
    sage_intacct.py       Interface defined; live sync on client demand
    dynamics365.py        Interface defined; live sync on client demand
  fx/                   Pluggable currency reference rate provider
    base.py               FXRateProvider interface
    frankfurter.py         Default: free, no API key (ECB rates)
    oanda.py               Drop-in OANDA implementation
  reconciliation/
    matcher.py             Bank-to-GL matching engine
    trial_balance.py       Trial balance tie-out
    flags.py                FX-rate-mismatch detection
  coa.py                     Chart of accounts: classifies each GL account
                              (revenue/COGS/opex/other income-expense/
                              asset/liability/equity), per entity
  reporting/
    profit_and_loss.py         Live P&L computation from GL activity
    pl_export.py                 .xlsx export: a GL Data tab + a P&L tab
                              where every figure is a real SUMIFS/SUM
                              formula, not a hardcoded number
  entities.py                Legal entity registry (which entity a report is against)
  skills/
    store.py                 The "evolving skill file": human feedback on a
                              flag becomes a KnownExceptionPattern, applied
                              to suppress the same reviewed noise later
  rag/
    store.py                 Per-entity document retrieval (TF-IDF, no
                              external deps) grounding chat answers in a
                              client's own policies/notes
  chat/
    tools.py                  The tools the chat agent can call (thin
                              wrappers over the engine/entity/RAG/skill code)
    agent.py                  The tool-use loop against the Claude API
    router.py                 POST /chat
  security/
    audit.py                  Append-only audit log (who did what, when)
    auth.py                   Minimal role-based access + segregation of duties
    pii.py                     Masking utilities applied before audit logging
  api/
    routes.py               FastAPI endpoints
    schemas.py               Request/response models
  store.py                  In-memory persistence (MVP only, see below)
  main.py                    FastAPI app entrypoint
web/
  index.html                  Minimal chat widget (type or speak) served at /app
tests/                       pytest suite -- matcher, tie-out, FX flagging,
                             entities, skills/feedback, RAG, chat tools,
                             security/segregation-of-duties, and the API
                             end to end
sample_data/                 A worked example: a bank statement, a GL
                              export, and a trial balance with one planted
                              exception, for demos and onboarding
k8s/                         Deployment manifests for this service
COMPLIANCE.md                What's actually implemented vs. out of scope
                              for GAAP/SOX/PII/HIPAA/securities -- read this
                              before telling a client anything about compliance
```

### Why a pluggable FX provider

The platform never depends on a specific currency data vendor. It depends
on `app.fx.base.FXRateProvider`. The default implementation
(`FrankfurterFXProvider`) uses the free ECB-based Frankfurter API so the
platform works out of the box with no account setup. Switching to OANDA
(or any other reference source) is a config change:

```
FX_PROVIDER=oanda
OANDA_API_KEY=...
```

No reconciliation code changes when the provider changes.

### Why bank reconciliation needs a scoped GL account

Both legs of a balanced journal entry share the same absolute amount, so
matching a bank feed against the *entire* GL can produce a coincidental
match against an unrelated expense or revenue line instead of the real
cash-side entry. Always pass `cash_account_codes` (the GL account code(s)
that represent the bank account in question) when running
`/reconciliations/run` against real data. `sample_data/` and the API test
demonstrate this.

### Known limitation: cross-currency matching

The matcher currently requires the bank transaction and GL entry to share
the same currency code. A bank feed that reports a transaction in a
foreign currency, matched against a GL entry that only records the
converted base-currency amount, will show up as unmatched rather than
matched-with-a-currency-note. The natural next step is to have the
matcher convert cross-currency amounts through the configured FX provider
before comparing, which would also let it flag "same transaction, wrong
conversion" instead of just "no match found."

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload
# API docs: http://127.0.0.1:8000/docs
```

### Try it with the sample data

```bash
curl -X POST http://127.0.0.1:8000/sources/upload \
  -F "bank_file=@sample_data/bank_statement_sample.csv" \
  -F "gl_file=@sample_data/gl_export_sample.csv" \
  -F "trial_balance_file=@sample_data/trial_balance_sample.csv"
# => {"source_id": "..."}

curl -X POST http://127.0.0.1:8000/reconciliations/run \
  -H "Content-Type: application/json" \
  -d '{"source_id": "<id>", "check_fx": false, "cash_account_codes": ["1000"]}'
# => {"reconciliation_id": "...", "summary": {...}}

curl http://127.0.0.1:8000/reconciliations/<reconciliation_id>/exceptions
curl http://127.0.0.1:8000/reconciliations/<reconciliation_id>/trial-balance
```

The sample data is deliberately imperfect: one bank wire with no GL
counterpart, one EUR bank transfer that only has a converted-USD GL leg
(demonstrating the cross-currency limitation above), and a $25 planted
variance on Facilities Expense so the tie-out flag has something to catch.

## Chat agent

`POST /chat` (and the widget at `/app/`) puts a conversational layer in
front of the same engine -- no new business logic, just tools wired to it
(`app/chat/tools.py`): list entities, run a close, list exceptions, check
a trial balance, search an entity's reference docs, and record feedback on
an exception.

Requires `ANTHROPIC_API_KEY` (or an `ant auth login` profile) in the
environment -- without it, `/chat` returns a clear "not configured" error
rather than crashing. Configuration, tuned for a *deterministic business
reporting* agent rather than a creative one:

| Env var | Default | Why |
|---|---|---|
| `CHAT_MODEL` | `claude-opus-4-8` | `claude-sonnet-5` is a reasonable cheaper choice for this well-scoped tool-calling task |
| `CHAT_MAX_TOKENS` | `4096` | Replies are short business answers, not long-form generation |
| `CHAT_EFFORT` | `medium` | Balances quality/cost for routing + reporting, not deep reasoning |
| `CHAT_THINKING` | unset | Set to `adaptive` to turn on extended thinking for harder queries |

Sampling parameters (temperature/top_p/top_k) aren't exposed: Opus 4.8
rejects non-default values outright, and determinism here comes from tight
tool schemas and a narrow system prompt, not from sampling.

### Multi-entity + the "evolving skill" feedback loop

Create an entity, tag uploaded sources to it, then ask the chat agent
about it by name:

```bash
curl -X POST "http://127.0.0.1:8000/entities?name=Acme+Ops+LLC&base_currency=USD"
curl -X POST http://127.0.0.1:8000/sources/upload -F entity_id=<id> -F bank_file=@... -F gl_file=@...

curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo", "message": "run the close for Acme Ops LLC"}'
```

When a reviewer confirms an exception is a known, recurring non-issue
(via chat, or `POST /feedback` directly), that decision is recorded per
entity and applied automatically on future runs -- see
`app/skills/store.py` and `skills_data/<entity_id>.md` (written at
runtime) for the human-readable record of what's been learned. This is a
deliberately narrow mechanism: patterns are only ever created from an
explicit human review, never invented by the model.

## Profit & loss

A live income statement, computed from GL activity for any date range --
not a cached or hand-built report. Requires classifying each GL account
first (`app/coa.py`): revenue, COGS, operating expense, other income,
other expense, or a balance-sheet type (asset/liability/equity, excluded
from the P&L). An account with GL activity but no classification is never
silently folded into Net Income -- it's listed separately as
`unclassified_account_codes` until someone classifies it.

```bash
# Classify accounts once per entity
curl -X POST http://127.0.0.1:8000/entities/<entity_id>/chart-of-accounts \
  -H "Content-Type: application/json" \
  -d '{"account_code": "4000", "account_name": "Revenue", "account_type": "revenue"}'

# Then ask for the P&L any time, for any period
curl "http://127.0.0.1:8000/entities/<entity_id>/profit-and-loss?period_start=2026-06-01&period_end=2026-06-30"

# Or download it as a live spreadsheet
curl "http://127.0.0.1:8000/entities/<entity_id>/profit-and-loss/export?period_start=2026-06-01&period_end=2026-06-30" \
  -o pl.xlsx
```

Also reachable conversationally: "give me the P&L for Acme Ops LLC for June."

**About the spreadsheet export.** The `.xlsx` has a `GL Data` tab (the
entity's full ledger) and a `P&L` tab where every line -- account amounts,
section subtotals, gross profit, operating income, net income -- is a real
`SUMIFS`/`SUM` formula referencing `GL Data` and two editable period cells
(`B2`/`B3`), not a pasted number. Change the period cells or re-paste
updated GL data and the whole report recalculates. This was built as an
explicit substitute for a proprietary tool's live-data Excel functions
(DataRails' `DR.GET`, used via their Excel add-in) -- `SUMIFS` is a
standard, verifiable Excel function that gets the same "live, not
hardcoded" outcome without guessing at a syntax we can't confirm from
outside that product. If you hold a DataRails license, this `GL Data` tab
is exactly the kind of source table their own functions would reference.

## Tests

```bash
pytest tests/ -v
```

## Deploying

```bash
docker build -t finance-close-platform:latest .
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.example.yaml   # copy, fill in real values first
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

**Deploying to Azure instead of a generic k8s cluster:** see
**[AZURE_DEPLOYMENT.md](./AZURE_DEPLOYMENT.md)**. The widget
(`web/`) and the backend (everything else) deploy separately -- Azure
Static Web Apps runs static content only, not this app's FastAPI process
-- via the two workflows in `.github/workflows/`. Set `ALLOWED_ORIGINS`
(backend) and `web/config.js`'s `API_BASE_URL` (widget) to match each
other once both are deployed; CORS support for this split is in
`app/main.py`.

## Security & compliance

`app/security/` implements an append-only audit log, PII masking applied
before anything is logged, and role-based access control with a real,
tested segregation-of-duties rule (a reviewer can't approve their own
reconciliation). See **[COMPLIANCE.md](./COMPLIANCE.md)** for exactly what
this does and doesn't claim -- in particular, HIPAA and securities-specific
controls are explicitly out of scope pending a confirmed client need,
rather than built speculatively or claimed without basis.

Set `AUTH_TOKENS` (e.g. `tok_alice:alice:preparer,tok_bob:bob:reviewer`) to
turn on role enforcement; unset, every request runs as an
unauthenticated/admin identity so local dev and the test suite work
without setup.

## Roadmap / not yet built

- **Persistent storage.** `app/store.py` is in-memory by design for this
  MVP -- swap it for Postgres (sources, reconciliation_runs, flags tables)
  before running this against real client data across multiple
  processes/restarts.
- **Live SaaS/ERP sync.** QuickBooks Online has a real OAuth + API
  implementation (`app/ingestion/quickbooks.py`) but needs an app
  registered with Intuit and a token-storage/refresh strategy wired to
  the store. NetSuite, Sage Intacct, and Dynamics 365 Finance adapters
  define the same interface but are stubs -- per the connector-priority
  rule, build the live implementation when a specific client needs it,
  not speculatively.
- **Cross-currency matching**, described above.
- **RAG corpus is currently seeded manually** (`app/rag/store.py`) -- no
  endpoint yet to upload a client's policy documents; add one when a real
  client's documents need indexing.
- **Real SSO/OIDC** in place of the bearer-token-to-role mapping in
  `app/security/auth.py`, once this runs somewhere beyond a demo.
