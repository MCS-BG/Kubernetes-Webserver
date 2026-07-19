# Step 3: Ingesting Data

Two ways to get data in: a one-time CSV/Excel upload (fully working today)
or a live SaaS/ERP connection (one real implementation, several defined
interfaces awaiting a client that needs them).

## CSV/Excel upload

```bash
curl -X POST http://127.0.0.1:8000/sources/upload \
  -F "bank_file=@sample_data/bank_statement_sample.csv" \
  -F "gl_file=@sample_data/gl_export_sample.csv" \
  -F "trial_balance_file=@sample_data/trial_balance_sample.csv" \
  -F "entity_id=<entity_id>"
```

```json
{"source_id":"981f47443eab480796824cdaa8afc2cc"}
```

All three files are optional -- upload just a GL file if that's all you
have. `entity_id` is optional too but you'll want it for anything past
raw reconciliation (P&L, chat, feedback are all entity-scoped). Every
upload creates a new source; nothing gets overwritten, and a P&L (Step 7)
pulls GL activity from **every** source ever uploaded for that entity, not
just the latest one.

### Expected column names

| File | Required columns |
|---|---|
| Bank statement | `date, amount, currency, description, reference, account` |
| GL export | `date, amount, currency, account_code, account_name, description, reference` |
| Trial balance | `account_code, account_name, debit, credit` |

Column names are configurable per-source if your export uses different
headers -- see `DEFAULT_BANK_COLUMNS` / `DEFAULT_GL_COLUMNS` /
`DEFAULT_TRIAL_BALANCE_COLUMNS` in `app/ingestion/csv_excel.py`. `.xlsx`
and `.xls` work the same way as `.csv`.

**Amount sign convention:** positive = debit, negative = credit. A bank
deposit is typically positive; a customer payment recorded as a GL credit
to Revenue is typically negative. Get this backwards and reconciliation
still runs, but trial balance tie-out (Step 4) and P&L (Step 7) numbers
will be inverted -- if a report looks exactly upside-down, check this
first.

**Precision:** amounts are read as exact text and converted straight to
`Decimal` -- never round-tripped through a floating-point column. This
matters for money; see the ingestion adapter's docstring in
`app/ingestion/csv_excel.py` if you're curious why that's called out
explicitly (a real bug here was found and fixed while building the P&L
feature).

## Live SaaS/ERP connectors

| Connector | Status |
|---|---|
| QuickBooks Online | Real OAuth 2.0 + Accounting API implementation (`app/ingestion/quickbooks.py`). Needs an app registered with Intuit and a token storage/refresh strategy -- **not live-tested in this environment**, since that requires real Intuit credentials. |
| NetSuite | Interface defined (`app/ingestion/netsuite.py`), not implemented. Build when a client on NetSuite needs it. |
| Sage Intacct | Interface defined (`app/ingestion/sage_intacct.py`), not implemented. |
| Dynamics 365 Finance | Interface defined (`app/ingestion/dynamics365.py`), not implemented. |

All connectors implement the same `SourceAdapter` interface
(`fetch_bank_transactions`, `fetch_gl_entries`, `fetch_trial_balance`), so
reconciliation and P&L don't care whether data came from a CSV or a live
API -- swapping the source is a config change, not a rewrite. This is
intentional: per the connector-priority rule, build the next live
integration when a specific client needs it, not speculatively.

## Next

[Step 4: Reconciliation](04-reconciliation.md)
