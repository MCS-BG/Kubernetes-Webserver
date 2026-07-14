# Step 6: Currency / FX Checks

For multi-currency entities: is the exchange rate that was actually
booked on a GL entry consistent with an independent reference rate, or
was it posted at a stale/wrong rate?

## How it works

Every `GLEntry` can optionally carry a `booked_fx_rate` -- the rate
actually used to convert that entry into the base/functional currency at
posting time. When `check_fx: true` is passed to
`POST /reconciliations/run` (the default), each entry with a
`booked_fx_rate` set and a currency different from the base currency gets
compared against a live reference rate:

```python
variance_bps = abs(booked_fx_rate - reference_rate) / reference_rate * 10000
```

If the variance exceeds `FX_MISMATCH_TOLERANCE_BPS` (default 50 bps), an
`fx_rate_mismatch` flag is raised -- `warning` severity under 4x the
tolerance, `critical` above it.

```json
{
  "type": "fx_rate_mismatch",
  "severity": "critical",
  "message": "Intercompany Receivable: entry booked EUR->USD at 1.1500, reference rate was 1.0800 (648.1 bps variance)",
  "details": {"currency": "EUR", "base_currency": "USD", "booked_rate": "1.1500", "reference_rate": "1.0800", "variance_bps": "648.1"}
}
```

## Honest gap: no ingestion path populates `booked_fx_rate` yet

This is fully implemented and unit-tested at the engine level
(`app/reconciliation/flags.py`, `tests/test_fx_flagging.py`), but **no
current adapter sets `booked_fx_rate` on ingestion** -- not the CSV/Excel
importer, not the QuickBooks adapter. In practice today, uploading real
data and running with `check_fx: true` will not raise any
`fx_rate_mismatch` flags, because every GL entry's `booked_fx_rate` is
`None`, regardless of currency. This isn't a silent failure (nothing
claims to have found a match when it hasn't), but it means the feature
needs one more piece of wiring -- either a `booked_fx_rate` column added
to the CSV import mapping, or populating it from whichever live connector
eventually carries that data -- before it does anything on real uploads.
Flag this before promising a client this check runs on their data.

## The reference rate source is pluggable

The platform never depends on a specific currency data vendor -- it
depends on the `FXRateProvider` interface (`app/fx/base.py`):

```bash
FX_PROVIDER=frankfurter   # default: free, no API key, ECB rates via api.frankfurter.dev
FX_PROVIDER=oanda         # requires OANDA_API_KEY
```

Switching providers is a config change, not a code change -- see
`app/fx/__init__.py`'s `get_fx_provider()` factory.

## Known limitation: cross-currency bank-to-GL matching

Separately from the FX-mismatch check above, the reconciliation *matcher*
(Step 4) requires a bank transaction and a GL entry to share the same
currency code to match at all. A bank feed reporting a transaction in EUR,
matched against a GL entry that only records the converted USD amount,
shows up as unmatched rather than "matched, currency-converted." The
natural fix is to have the matcher convert cross-currency amounts through
the configured `FXRateProvider` before comparing -- not yet built.

## Next

[Step 7: Profit & Loss](07-profit-and-loss.md)
