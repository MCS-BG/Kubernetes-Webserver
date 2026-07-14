# Close & Reconciliation Platform

Automated bank-to-GL reconciliation and trial-balance tie-out for Two
Rivers Advisory. Ingests a bank feed, a general ledger, and a reported
trial balance (via live SaaS/ERP API or a CSV/Excel export), matches
transactions across them, and flags exactly which line items don't
reconcile and why -- so a close that took days of manual matching takes
minutes of reviewing exceptions instead.

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
5. **Surfaces** every exception through a small HTTP API, ready to sit
   behind a dashboard or a chat interface.

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
  api/
    routes.py               FastAPI endpoints
    schemas.py               Request/response models
  store.py                  In-memory persistence (MVP only, see below)
  main.py                    FastAPI app entrypoint
tests/                       pytest suite for the matcher, tie-out, FX
                              flagging, and the API end to end
sample_data/                 A worked example: a bank statement, a GL
                              export, and a trial balance with one planted
                              exception, for demos and onboarding
k8s/                         Deployment manifests for this service
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
- **Conversational/chat interface, RAG, multi-entity routing, and a
  compliance posture (GAAP/SOX/PII and beyond)** are being scoped as a
  distinct next phase on top of this engine.
