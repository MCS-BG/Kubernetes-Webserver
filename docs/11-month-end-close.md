# Step 11: Month-End Close Workflow

Reconciliation and P&L answer "what does the ledger say." This step
answers the separate question of "has this period actually been signed
off, by whom, and if not, why" -- an explicit state machine per legal
entity + period, not a status someone tracks in a spreadsheet or their
head.

## States

```
not_started -> in_progress -> pending_review -> approved
                                              -> rejected -> (resubmit) -> pending_review
```

| Status | Meaning |
|---|---|
| `not_started` | No close has been begun for this entity + period yet |
| `in_progress` | Begun, not yet submitted for review (or submission was blocked -- see below) |
| `pending_review` | Submitted; waiting on a reviewer's sign-off |
| `approved` | Reviewer signed off -- terminal for this period |
| `rejected` | Reviewer sent it back with a reason; resubmitting moves it back to `pending_review` |

## Starting a close

```bash
curl -X POST http://127.0.0.1:8000/close/start \
  -H "Authorization: Bearer tok_alice_prep" -H "Content-Type: application/json" \
  -d '{"entity_id": "<entity_id>", "period_start": "2026-06-01", "period_end": "2026-06-30"}'
```

```json
{"id":"7c7800ddfa344fd49659d992b2139051","entity_id":"91ad3267cf82408eb84642d2d7e6f03d","period_start":"2026-06-01","period_end":"2026-06-30","status":"in_progress","reconciliation_id":null,"prepared_by":null,"reviewed_by":null,"rejection_reason":null,"history":[{"timestamp":"2026-07-19T19:12:46.825771+00:00","actor":"alice","from_status":"not_started","to_status":"in_progress","note":""}]}
```

(Real output, from a live run against this exact endpoint.) Idempotent --
calling it again for the same entity + period returns the same period
untouched, whatever status it's already reached.

## Submitting for review -- blocked by open critical exceptions

```bash
curl -X POST http://127.0.0.1:8000/close/submit \
  -H "Authorization: Bearer tok_alice_prep" -H "Content-Type: application/json" \
  -d '{"close_id": "<close_id>", "reconciliation_id": "<reconciliation_id>"}'
```

If the linked reconciliation still has open `critical`-severity flags
(see [Step 5](05-exceptions-and-feedback.md)), this returns `400`:

```json
{"detail":"2 unresolved critical exception(s) on this reconciliation -- resolve or suppress them (see POST /feedback) before submitting for review."}
```

The close stays `in_progress` -- this is the concrete, queryable answer to
"why hasn't month-end closed": either nobody's started it, it's sitting in
a reviewer's queue, or it's blocked by a specific, countable set of
exceptions on a specific reconciliation run. Once those are resolved or
suppressed, resubmitting the same call succeeds:

```json
{"id":"7c7800ddfa344fd49659d992b2139051", "...":"...", "status":"pending_review","reconciliation_id":"6132ecf5381a42eaae96692da88ca646","prepared_by":"alice", "...":"..."}
```

## Approving or rejecting -- segregation of duties enforced

Same rule as `/feedback` ([Step 9](09-security-roles-audit.md)): the
reviewer signing off cannot be the same actor who submitted it.

```bash
# Alice (the preparer) tries to approve her own submission
curl -X POST http://127.0.0.1:8000/close/approve \
  -H "Authorization: Bearer tok_alice_rev" -H "Content-Type: application/json" \
  -d '{"close_id": "<close_id>"}'
# -> 403 "Segregation of duties: the reviewer approving this close cannot
#    be the same person who submitted it for review."

# Bob (a different actor, reviewer role) approves instead -- allowed
curl -X POST http://127.0.0.1:8000/close/approve \
  -H "Authorization: Bearer tok_bob_rev" -H "Content-Type: application/json" \
  -d '{"close_id": "<close_id>"}'
```

```json
{"id":"7c7800ddfa344fd49659d992b2139051","...":"...","status":"approved","reconciliation_id":"6132ecf5381a42eaae96692da88ca646","prepared_by":"alice","reviewed_by":"bob","rejection_reason":null,"history":[
  {"timestamp":"2026-07-19T19:12:46.825771+00:00","actor":"alice","from_status":"not_started","to_status":"in_progress","note":""},
  {"timestamp":"2026-07-19T19:12:46.856653+00:00","actor":"alice","from_status":"in_progress","to_status":"pending_review","note":""},
  {"timestamp":"2026-07-19T19:12:46.872320+00:00","actor":"bob","from_status":"pending_review","to_status":"approved","note":""}
]}
```

(Real output -- the full `history` array is an append-only record of every
transition: who, when, from what status to what status.)

Rejecting is the same shape, with a required reason:

```bash
curl -X POST http://127.0.0.1:8000/close/reject \
  -H "Authorization: Bearer tok_bob_rev" -H "Content-Type: application/json" \
  -d '{"close_id": "<close_id>", "reason": "Missing Q2 accrual, please add it"}'
```

A rejected close's `rejection_reason` clears automatically the moment it's
successfully resubmitted via `/close/submit` -- it only reflects the
*current* blocker, not history (the `history` array is where past
rejections live).

## Reading status

```bash
curl http://127.0.0.1:8000/close/<close_id>
curl http://127.0.0.1:8000/entities/<entity_id>/close
```

The second lists every close period ever started for that entity, oldest
first -- no role required, these are read-only.

## Endpoints and roles

| Endpoint | Method | Minimum role | Notes |
|---|---|---|---|
| `/close/start` | POST | `preparer` | Idempotent per entity + period |
| `/close/submit` | POST | `preparer` | Blocked by open critical flags; entity of the reconciliation must match the close period's entity |
| `/close/approve` | POST | `reviewer` | Segregation of duties enforced |
| `/close/reject` | POST | `reviewer` | Segregation of duties enforced; requires `reason` |
| `/close/{close_id}` | GET | none | Read-only |
| `/entities/{entity_id}/close` | GET | none | Read-only |

Every transition is also written to the audit log (`close_started`,
`close_submitted`, `close_approved`, `close_rejected`) -- see
[Step 9](09-security-roles-audit.md).

## Asking the chat agent

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo", "message": "why hasn'"'"'t month-end closed for Acme Ops LLC for June 2026?"}'
```

Routes to the `get_close_status` tool, which reports the real status plus,
if blocked, the count of open critical exceptions and which reconciliation
they're on. This tool is **read-only by design**: starting, submitting,
approving, and rejecting all stay REST-only, because segregation of duties
only means something with a real authenticated identity, and the chat
session (see [Step 8](08-chat-agent-and-widget.md)) doesn't carry one.

## What this doesn't do (yet)

Like the rest of this MVP, close periods live in the in-memory
`CloseWorkflowStore` (`app/close/workflow.py`) -- they don't survive a
process restart. The same swap-to-Postgres note in `app/store.py` applies
here before running this against real client data across multiple
processes or restarts. There's also no reminder/notification when a close
sits in `pending_review` too long, and no configurable multi-step approval
chain (one reviewer signs off, not a chain of them) -- both reasonable
future additions, not built here.

## Next

[Step 10: Deployment](10-deployment.md) -- this feature needs no new
infrastructure, secrets, or environment variables; it ships in the same
container image as everything else.
