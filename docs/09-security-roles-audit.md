# Step 9: Security, Roles & Audit

For the compliance framing (what this supports vs. explicitly doesn't
claim -- GAAP/SOX/PII/HIPAA/securities), see
**[../COMPLIANCE.md](../COMPLIANCE.md)**. This step is the operational
how-to for the technical controls that doc describes.

## Turning on role-based access control

Unset (the default), every request runs as a fixed `("unauthenticated",
"admin")` identity -- everything is allowed, nothing is segregated. This
is intentional for local dev and the test suite. To make roles real, set:

```bash
export AUTH_TOKENS="tok_alice:alice:preparer,tok_bob:bob:reviewer,tok_carol:carol:admin"
```

Format: comma-separated `token:actor_name:role` triples. Three roles,
ranked `preparer < reviewer < admin` -- a higher role satisfies any
endpoint requiring a lower one.

| Endpoint | Minimum role |
|---|---|
| `POST /sources/upload` | `preparer` |
| `POST /reconciliations/run` | `preparer` |
| `POST /feedback` | `reviewer` |
| `GET /audit-log` | `reviewer` |
| `POST /entities/{id}/chart-of-accounts` | `preparer` |
| `POST /close/start` | `preparer` |
| `POST /close/submit` | `preparer` |
| `POST /close/approve` | `reviewer` |
| `POST /close/reject` | `reviewer` |

Send the token as a bearer header:

```bash
curl -X POST http://127.0.0.1:8000/reconciliations/run \
  -H "Authorization: Bearer tok_alice" \
  -H "Content-Type: application/json" \
  -d '{"source_id": "<source_id>", "check_fx": false}'
```

Missing/invalid token with `AUTH_TOKENS` configured -> `401`. Valid token,
insufficient role -> `403`.

## Segregation of duties (tested, not just documented)

`POST /feedback` enforces that the reviewer approving an exception cannot
be the same actor who ran the reconciliation it came from -- even if that
actor holds both roles via two different tokens:

```bash
# alice (preparer) runs the reconciliation
curl -X POST http://127.0.0.1:8000/reconciliations/run \
  -H "Authorization: Bearer tok_alice_prep" -H "Content-Type: application/json" \
  -d '{"source_id": "<source_id>", "check_fx": false}'

# alice, now using her reviewer token, tries to approve her own exception
curl -X POST http://127.0.0.1:8000/feedback \
  -H "Authorization: Bearer tok_alice_rev" -H "Content-Type: application/json" \
  -d '{"reconciliation_id": "<id>", "flag_index": 0, "match_text": "x", "note": "n"}'
# -> 403 "Segregation of duties: the reviewer approving this exception
#    cannot be the same person who ran the reconciliation it came from."

# bob (a different actor, reviewer role) approves it instead -- allowed
curl -X POST http://127.0.0.1:8000/feedback \
  -H "Authorization: Bearer tok_bob_rev" -H "Content-Type: application/json" \
  -d '{"reconciliation_id": "<id>", "flag_index": 0, "match_text": "x", "note": "n"}'
# -> 200
```

See `tests/test_segregation_of_duties.py` for the full working example
this was copied from. `POST /close/approve` and `POST /close/reject`
enforce the identical rule against the close's `prepared_by` actor -- see
[Step 11](11-month-end-close.md) and `tests/test_close.py`.

## The audit log

Every source upload, reconciliation run, and feedback recording is
logged -- who, when, which entity, what action:

```bash
curl http://127.0.0.1:8000/audit-log -H "Authorization: Bearer tok_bob_rev"
```

```json
{"entries":[
  {"id":"...","timestamp":"2026-07-14T...","actor":"alice","action":"reconciliation_run","entity_id":"...","details":{"reconciliation_id":"...","source_id":"..."}}
]}
```

Filter to one entity: `GET /audit-log?entity_id=<entity_id>`. The
`AuditLog` class (`app/security/audit.py`) has no update or delete
method -- there is no code path that can rewrite history, by
construction, not just by convention.

## PII masking

Free-text values are masked before they're written to the audit log
(`app/security/pii.py`), so the audit trail itself can't become a second
place PII leaks from -- e.g. `"Wire ref 123456789"` is logged as
`"Wire ref *****6789"`. This runs automatically; there's nothing to turn
on.

## Next

[Step 10: Deployment](10-deployment.md)
