# Step 7: Profit & Loss

A live income statement -- computed fresh from GL activity for any date
range every time it's requested, never a cached or hand-assembled report.
Requires the chart of accounts from [Step 2](02-entities-and-chart-of-accounts.md)
to be set up first.

## Get it via the API

```bash
curl "http://127.0.0.1:8000/entities/<entity_id>/profit-and-loss?period_start=2026-06-01&period_end=2026-06-30"
```

```json
{
  "entity_id": "d3185ecdc4644831964b6e763f72ec6b",
  "period_start": "2026-06-01",
  "period_end": "2026-06-30",
  "revenue": {"lines": [{"account_code": "4000", "account_name": "Revenue", "amount": "25000.00"}], "total": "25000.00"},
  "cogs": {"lines": [{"account_code": "5000", "account_name": "Cost of Goods Sold", "amount": "10000.00"}], "total": "10000.00"},
  "gross_profit": "15000.00",
  "operating_expenses": {"lines": [{"account_code": "6100", "account_name": "Facilities Expense", "amount": "2000.00"}], "total": "2000.00"},
  "operating_income": "13000.00",
  "other_income": {"lines": [], "total": "0"},
  "other_expense": {"lines": [], "total": "0"},
  "net_income": "13000.00",
  "unclassified_account_codes": []
}
```

(Real output, from actually running this exact sequence: create an
entity, classify 3 accounts, upload a 3-line GL export, request the P&L.)

If any account had GL activity but no chart-of-accounts entry, its code
appears in `unclassified_account_codes` and its activity is **excluded**
from every total above -- never silently guessed into Revenue or Expense.

## Get it conversationally

Through the [chat agent](08-chat-agent-and-widget.md): "give me the P&L
for Acme Ops LLC for June" -- the `get_profit_and_loss` tool calls the same
computation, formatted as text.

## Download it as a live spreadsheet

```bash
curl "http://127.0.0.1:8000/entities/<entity_id>/profit-and-loss/export?period_start=2026-06-01&period_end=2026-06-30" \
  -o pl.xlsx
```

The workbook has two tabs:

- **`GL Data`** -- the entity's *entire* ledger (not period-filtered), one
  row per GL entry: date, account code, account name, amount.
- **`P&L`** -- editable period cells (`B2`/`B3`, defaulted to the period
  you requested), and every figure below them is a formula, never a
  pasted number:

```
Revenue (4000)              =-SUMIFS('GL Data'!$D$2:$D$100000, 'GL Data'!$B$2:$B$100000, "4000", 'GL Data'!$A$2:$A$100000, ">="&$B$2, 'GL Data'!$A$2:$A$100000, "<="&$B$3)
Total Revenue                =SUM(B6:B6)
Cost of Goods Sold (5000)   =SUMIFS('GL Data'!$D$2:$D$100000, 'GL Data'!$B$2:$B$100000, "5000", ...)
Total Cost Of Goods Sold     =SUM(B10:B10)
Gross Profit                 =B7-B11
Facilities Expense (6100)   =SUMIFS(..., "6100", ...)
Total Operating Expenses     =SUM(B16:B16)
Operating Income             =B13-B17
NET INCOME                   =B19+B22-B25
```

Change the period cells, or paste in updated GL data, and the whole
report recalculates -- no regeneration needed. `SUMIFS`/`SUM` are
standard, verifiable Excel functions, used deliberately instead of any
proprietary vendor's live-data function syntax (e.g. DataRails' `DR.GET`)
that can't be confirmed from outside that product. If you hold a license
for a tool like that, the `GL Data` tab is exactly the kind of source
table its own functions would reference -- swapping formula syntax on top
of this same structure is a small follow-up, not a redesign.

Unclassified accounts appear at the bottom of the `P&L` tab under their
own heading, each with its own `SUMIFS` total, clearly separated from Net
Income above -- visible, not dropped.

## Next

[Step 8: Chat Agent & Web Widget](08-chat-agent-and-widget.md)
