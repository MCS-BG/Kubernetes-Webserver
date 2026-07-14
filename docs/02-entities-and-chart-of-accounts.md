# Step 2: Entities & Chart of Accounts

Every piece of data in this platform -- a bank feed, a GL export, a P&L --
belongs to a **legal entity**. This is what makes "which entity is this
reporting against" an answerable question, including through the chat
agent (Step 8).

## Create an entity

```bash
curl -X POST "http://127.0.0.1:8000/entities?name=Acme%20Ops%20LLC&base_currency=USD"
```

```json
{"id":"5f548f3f92d24e7098e6ae1f65453a6c","name":"Acme Ops LLC","base_currency":"USD"}
```

Save the `id` -- every other step needs it. `base_currency` matters for
the FX mismatch check (Step 6). An optional `description` param helps the
chat agent disambiguate entities with similar names.

## List entities

```bash
curl http://127.0.0.1:8000/entities
```

```json
{"entities":[{"id":"5f548f3f92d24e7098e6ae1f65453a6c","name":"Acme Ops LLC","base_currency":"USD","description":""}]}
```

## Classify the chart of accounts

Before this entity's GL activity can appear in a trial balance tie-out
breakdown by type or a P&L, each account code needs a type. This is a
one-time setup per entity (or whenever a new account is added to the
client's books).

```bash
curl -X POST http://127.0.0.1:8000/entities/<entity_id>/chart-of-accounts \
  -H "Content-Type: application/json" \
  -d '{"account_code": "4000", "account_name": "Revenue", "account_type": "revenue"}'

curl -X POST http://127.0.0.1:8000/entities/<entity_id>/chart-of-accounts \
  -H "Content-Type: application/json" \
  -d '{"account_code": "5000", "account_name": "Cost of Goods Sold", "account_type": "cogs"}'

curl -X POST http://127.0.0.1:8000/entities/<entity_id>/chart-of-accounts \
  -H "Content-Type: application/json" \
  -d '{"account_code": "6100", "account_name": "Facilities Expense", "account_type": "operating_expense"}'

curl -X POST http://127.0.0.1:8000/entities/<entity_id>/chart-of-accounts \
  -H "Content-Type: application/json" \
  -d '{"account_code": "1000", "account_name": "Cash", "account_type": "asset"}'
```

Valid `account_type` values (`app/coa.py`):

| Type | Meaning | Appears in P&L? |
|---|---|---|
| `revenue` | Sales/income accounts | Yes |
| `cogs` | Direct cost of delivering the sale | Yes |
| `operating_expense` | Overhead (rent, software, salaries, ...) | Yes |
| `other_income` | Non-operating income (e.g. interest) | Yes, below Operating Income |
| `other_expense` | Non-operating expense (e.g. interest expense) | Yes, below Operating Income |
| `asset` | Balance sheet | No |
| `liability` | Balance sheet | No |
| `equity` | Balance sheet | No |

Posting to the same `account_code` again overwrites the entry (useful for
correcting a misclassification -- there's no separate "update" endpoint,
`POST` is idempotent per account code).

## View what's classified so far

```bash
curl http://127.0.0.1:8000/entities/<entity_id>/chart-of-accounts
```

```json
{"accounts":[
  {"account_code":"4000","account_name":"Revenue","account_type":"revenue"},
  {"account_code":"5000","account_name":"Cost of Goods Sold","account_type":"cogs"},
  {"account_code":"6100","account_name":"Facilities Expense","account_type":"operating_expense"},
  {"account_code":"1000","account_name":"Cash","account_type":"asset"}
]}
```

## What happens if you skip this step

Nothing breaks -- reconciliation (Step 4) doesn't need a chart of
accounts at all. But the P&L (Step 7) will report every account it sees
GL activity for and hasn't been told the type of as
`unclassified_account_codes`, and deliberately **excludes** that activity
from Net Income rather than guessing. Classify accounts before asking for
a P&L on real data.

## Next

[Step 3: Ingesting Data](03-ingesting-data.md)
