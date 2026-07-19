# Step 1: Setup

## Install

```bash
git clone <this-repo>
cd Kubernetes-Webserver
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run it

```bash
uvicorn app.main:app --reload
```

- API + interactive docs: `http://127.0.0.1:8000/docs`
- Health check: `curl http://127.0.0.1:8000/health` -> `{"status":"ok"}`
- Chat widget: `http://127.0.0.1:8000/app/`
- **Demo dashboard: `http://127.0.0.1:8000/app/demo.html`** -- the fastest
  way to see the whole platform at once. Loads automatically, no curl
  commands required: seeds a demo entity from this repo's own
  `sample_data/`, then shows the reconciliation summary, trial balance
  tie-out, exceptions, and a live P&L (Sumly) side by side with the chat
  agent (Ledge + Sumly). See [Step 8](08-chat-agent-and-widget.md).

There's no database to provision and nothing else to start -- persistence
is in-memory by design for this stage (see README -> Roadmap). Restarting
the process clears all sources, reconciliation runs, entities, and chart
of accounts.

## Environment variables

None of these are required to run the app locally with default behavior.
Set the ones relevant to what you're doing.

| Variable | Used for | Default |
|---|---|---|
| `CHAT_PROVIDER` | Which LLM backs the chat agent (Step 8): `anthropic`, `openai`, or `xai`. | `anthropic` |
| `ANTHROPIC_API_KEY` | Required if `CHAT_PROVIDER=anthropic` (the default). Without it, `/chat` returns a clear "not configured" error instead of crashing. | unset |
| `OPENAI_API_KEY` | Required if `CHAT_PROVIDER=openai`. | unset |
| `XAI_API_KEY` | Required if `CHAT_PROVIDER=xai`. | unset |
| `CHAT_MODEL` | Which model the selected provider uses. Default depends on `CHAT_PROVIDER`: `claude-opus-4-8` (anthropic), `gpt-4o` (openai), `grok-4` (xai). | see left |
| `CHAT_MAX_TOKENS` | Max reply length -- Anthropic provider only. | `4096` |
| `CHAT_EFFORT` | Reasoning effort (`low`/`medium`/`high`/`xhigh`/`max`) -- Anthropic provider only. | `medium` |
| `CHAT_THINKING` | Set to `adaptive` to turn on extended thinking -- Anthropic provider only. | unset (off) |
| `FX_PROVIDER` | Currency reference source: `frankfurter` (free, no key) or `oanda`. | `frankfurter` |
| `OANDA_API_KEY` | Required only if `FX_PROVIDER=oanda`. | unset |
| `BASE_CURRENCY` | Default base/functional currency for FX and P&L checks. | `USD` |
| `MATCH_DATE_WINDOW_DAYS` | Reconciliation matcher tolerance (Step 4). | `3` |
| `MATCH_AMOUNT_TOLERANCE` | Reconciliation matcher amount tolerance. | `0.01` |
| `TIE_OUT_TOLERANCE` | Trial balance tie-out tolerance. | `0.01` |
| `FX_MISMATCH_TOLERANCE_BPS` | Currency mismatch threshold, in basis points (Step 6). | `50` |
| `ALLOWED_ORIGINS` | CORS allow-list, comma-separated. Only needed if the web widget is hosted on a different origin than this API (see Step 10 / AZURE_DEPLOYMENT.md). | unset (no CORS) |
| `AUTH_TOKENS` | Turns on role-based access control (Step 9). Format: `token:actor:role,token:actor:role`. | unset (everyone is an unauthenticated admin) |

## Confirming it actually works

```bash
pytest tests/ -v
```

88 tests should pass. If they don't, something in your environment
differs from what this was built against (Python 3.11, the pinned
versions in `requirements.txt`) -- fix that before proceeding, since every
later step assumes a working install.

## Next

[Step 2: Entities & Chart of Accounts](02-entities-and-chart-of-accounts.md)
