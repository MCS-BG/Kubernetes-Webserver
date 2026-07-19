# Step 4: Reconciliation

The core of the platform: match a bank feed against the GL, tie out the
trial balance, and surface exactly what doesn't reconcile and why.

## Run it

```bash
curl -X POST http://127.0.0.1:8000/reconciliations/run \
  -H "Content-Type: application/json" \
  -d '{"source_id": "<source_id>", "check_fx": false, "cash_account_codes": ["1000"]}'
```

```json
{"reconciliation_id":"57fcc3bb4aca4a779850d829b33971d2","summary":{"matched":3,"unmatched_bank":2,"unmatched_gl":2,"flags_total":5,"flags_by_severity":{"warning":4,"critical":1},"suppressed_by_learned_patterns":0}}
```

(This is real output, from running the platform's own `sample_data/`
files through this exact call.)

### `cash_account_codes` is not optional in practice

Both legs of a balanced journal entry share the same absolute amount, so
matching a bank feed against the **entire** GL can produce a coincidental
match against an unrelated expense or revenue line instead of the real
cash-side entry. Always pass the GL account code(s) that represent the
bank account(s) this feed belongs to. Skipping it doesn't error -- it
just silently produces worse matches, which is the kind of mistake that's
easy to miss until the exception list looks wrong.

### Request options

| Field | Default | Purpose |
|---|---|---|
| `source_id` | required | From Step 3's upload response |
| `cash_account_codes` | none (matches against all GL) | See above -- set this |
| `date_window_days` | `3` (env `MATCH_DATE_WINDOW_DAYS`) | How many days apart a bank txn and GL entry can be and still match |
| `amount_tolerance` | `0.01` (env `MATCH_AMOUNT_TOLERANCE`) | How close two amounts need to be to count as equal |
| `fuzzy_threshold` | `0.6` (env `FUZZY_DESCRIPTION_THRESHOLD`) | Minimum description-similarity score for a fuzzy match |
| `check_fx` | `true` | Whether to also run the currency mismatch check -- see [Step 6](06-currency-fx-checks.md) |
| `base_currency` | entity's configured currency, else `USD` | Used only if `check_fx` is true |

### How matching works

Four passes, each more permissive than the last, so what's left over at
the end is a genuine exception, not noise:

1. **Exact** -- same amount, same date, same currency.
2. **Date window** -- same amount, within `date_window_days` of each other (handles clearing delay).
3. **Fuzzy description** -- same amount, similar description/reference, any date (handles same transaction posted well outside the date window).
4. **Amount mismatch** -- same day, clearly the same transaction by description, but the amount is off. Flagged specifically as `amount_mismatch` rather than left as two separate unmatched entries.

Whatever doesn't match any pass becomes an `unmatched_bank` or
`unmatched_gl` flag. Exact duplicate entries (same date/amount/currency/
description appearing twice) are flagged as `duplicate_transaction`
regardless of matching.

## Trial balance tie-out

Runs automatically as part of `/reconciliations/run` (not a separate call)
-- its flags are merged into the same result. To see the account-by-account
detail:

```bash
curl http://127.0.0.1:8000/reconciliations/<reconciliation_id>/trial-balance
```

```json
{"accounts":[
  {"account_code":"1000","account_name":"Cash","computed_debit":"15000.00","computed_credit":"60350.50","reported_debit":"15000.00","reported_credit":"60350.50","tied_out":true},
  {"account_code":"6100","account_name":"Facilities Expense","computed_debit":"1200.00","computed_credit":"0","reported_debit":"1225.00","reported_credit":"0.00","tied_out":false}
]}
```

Two checks happen here: does each account's *computed* activity (from the
GL entries you uploaded) match what the trial balance *export* reported,
and does the ledger balance at all (total debits == total credits,
independent of any one account)? The example above is
`sample_data/trial_balance_sample.csv`'s planted $25 variance on
Facilities Expense, deliberately included so there's something for the
tie-out check to actually catch.

A reconciliation's critical flags are also what gates the month-end close
workflow -- see [Step 11](11-month-end-close.md): a close can't be
submitted for review while any are still open.

## Next

[Step 5: Exceptions & Feedback](05-exceptions-and-feedback.md)
