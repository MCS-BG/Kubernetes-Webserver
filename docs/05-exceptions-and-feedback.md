# Step 5: Exceptions & Feedback

## Reviewing exceptions

```bash
curl http://127.0.0.1:8000/reconciliations/<reconciliation_id>/exceptions
```

```json
{"flags":[
  {"type":"unmatched_bank","severity":"warning","message":"Bank transaction WIRE-771 for 8600.0 USD on 2026-06-27 has no matching GL entry","entry_ids":["8d8041eafd8c4a0db4592a152f75eb9e"],"details":{"amount":"8600.0","currency":"USD","date":"2026-06-27"}},
  {"type":"account_tie_out_mismatch","severity":"critical","message":"Account 6100 (Facilities Expense) doesn't tie out: computed debit/credit 1200.0/0 vs reported 1225.0/0.0","entry_ids":[],"details":{"account_code":"6100","debit_variance":"-25.0","credit_variance":"0.0"}}
]}
```

Every flag has an index (its position in this array -- the first flag is
index `0`) -- that index is what you reference when recording feedback
below. Flag types: `unmatched_bank`, `unmatched_gl`, `amount_mismatch`,
`duplicate_transaction`, `fx_rate_mismatch`, `account_tie_out_mismatch`,
`trial_balance_out_of_balance`. Severity is `warning` or `critical`.

## Teaching the system to stop re-flagging known noise

This is the platform's "learning" mechanism, and it's deliberately
narrow: a pattern is only ever created from an explicit human review,
never invented by the model or the matcher on its own.

```bash
curl -X POST http://127.0.0.1:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "reconciliation_id": "<reconciliation_id>",
    "flag_index": 0,
    "match_text": "Vendor X",
    "note": "Vendor X always pays 5 days late -- not a real reconciliation issue"
  }'
```

```json
{"pattern_id":"...","entity_id":"<entity_id>","flag_type":"unmatched_bank"}
```

From then on, any future flag of the same type whose message or details
contain `match_text` (case-insensitive substring match) is suppressed for
that entity -- automatically, on every future `/reconciliations/run` call.
The reconciliation summary reports how many were suppressed:

```json
{"summary": {"...": "...", "suppressed_by_learned_patterns": 1}}
```

### Where this is recorded

Two places, on purpose:

- **In memory**, consulted by the matcher/flagging code on every run
  (`app/skills/store.py`) -- this is what actually changes behavior.
- **`skills_data/<entity_id>.md`**, a human-readable markdown file
  written at runtime -- this is the audit trail a comptroller (or the
  chat agent) can read to see what's been learned and why. It's
  regenerated on every new pattern for that entity; don't hand-edit it,
  since edits there don't feed back into the suppression logic --
  `POST /feedback` is the only way to add a pattern.

### Who's allowed to record feedback

`/feedback` requires the `reviewer` role, and enforces segregation of
duties: the reviewer approving an exception can't be the same actor who
ran the reconciliation it came from. See [Step 9](09-security-roles-audit.md)
for how roles are configured -- with no `AUTH_TOKENS` configured (the
default), everyone is the same `unauthenticated` actor and this check is
effectively off, since there's no real identity to segregate.

## Next

[Step 6: Currency / FX Checks](06-currency-fx-checks.md)
