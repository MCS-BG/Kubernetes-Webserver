# Step 8: Chat Agent & Web Widget

Every capability in Steps 2-7 is also reachable conversationally -- ask
for a close, an exception list, or a P&L in plain language instead of
constructing HTTP calls.

## Requirements

`ANTHROPIC_API_KEY` must be set in the environment (or an `ant auth login`
profile active). Without it, `/chat` returns a clear error instead of
crashing:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo", "message": "list entities"}'
```

```json
{"detail":"Chat agent is not configured: \"Could not resolve authentication method. Expected one of api_key, auth_token, or credentials to be set. Or for one of the `X-Api-Key` or `Authorization` headers to be explicitly omitted\""}
```

(Real output, from running this exact call with no key configured --
this is the actual failure mode, not a hypothetical one.)

## Talking to it

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo", "message": "run the close for Acme Ops LLC"}'
```

```json
{"reply": "..."}
```

`session_id` is any string you choose -- conversation history persists
in-memory per session (`app/chat/agent.py`), so reuse the same ID across
calls to keep context (e.g. "now show me the exceptions" after a close
run, without repeating the entity name). Reset a session:

```bash
curl -X POST http://127.0.0.1:8000/chat/demo/reset
```

### What the agent can do

Every tool in `app/chat/tools.py` maps directly to an API call from
earlier steps -- the chat layer adds no new business logic, only natural
language routing to it:

| Ask it to... | Tool called |
|---|---|
| List entities | `list_entities` |
| Run a close for an entity | `run_reconciliation` |
| List exceptions from a run | `get_exceptions` |
| Check a trial balance | `get_trial_balance_report` |
| Search an entity's policy docs | `search_knowledge_base` |
| Mark an exception as a known non-issue | `record_exception_feedback` |
| Get a P&L for a date range | `get_profit_and_loss` |
| Check whether month-end has closed for a period, and why not | `get_close_status` |

`get_close_status` is read-only by design -- starting, submitting,
approving, or rejecting a close stays REST-only (see
[Step 11](11-month-end-close.md)), since segregation of duties needs a
real authenticated identity, and a chat session doesn't carry one.

### Multiple LLM providers

The chat agent's LLM is pluggable (`app/chat/providers/`), the same way
the FX reference-rate source is (`app/fx/`): `/chat` and the agent loop
only ever depend on the `ChatProvider` interface, never a specific
vendor's SDK. Set `CHAT_PROVIDER`:

| `CHAT_PROVIDER` | Backend | Required key | Default model |
|---|---|---|---|
| `anthropic` (default) | Claude | `ANTHROPIC_API_KEY` | `claude-opus-4-8` |
| `openai` | ChatGPT | `OPENAI_API_KEY` | `gpt-4o` |
| `xai` | Grok | `XAI_API_KEY` | `grok-4` |
| `perplexity` | Perplexity Sonar | `PERPLEXITY_API_KEY` | `sonar-pro` |

Override the model with `CHAT_MODEL` regardless of provider. All four
reuse the exact same tools (`app/chat/tools.py`) and the exact same
`SYSTEM_PROMPT` (`app/chat/agent.py`) -- switching providers is a config
change, not a rewrite of what the agent can do.

The mechanics differ under the hood: Anthropic's SDK has a built-in
`tool_runner` that loops through tool calls automatically
(`app/chat/providers/anthropic_provider.py`). OpenAI's SDK has no such
loop, so the OpenAI/xAI/Perplexity provider hand-rolls it
(`app/chat/providers/openai_compatible.py`): call the model, check for
`tool_calls`, execute each one via the tool's own `.call(...)`, feed the
result back as a `tool`-role message, repeat (capped at 8 rounds as a
runaway-loop guard). xAI's Grok API and Perplexity's Sonar API are both
OpenAI-wire-compatible, so they're the same provider class pointed at a
different `base_url` and key -- not separate implementations.

**Perplexity caveat:** wire-compatibility isn't the same thing as
tool-calling support, and Sonar's support for the `tools` parameter isn't
confirmed reliable at the time this was written. If it doesn't honor
tools the way OpenAI/xAI do, a Perplexity-backed chat can still answer in
prose, but it will never actually call `run_reconciliation`,
`get_close_status`, `get_profit_and_loss`, or anything else in
`app/chat/tools.py` -- it would just be an ungrounded Q&A bot layered on
top of an app whose entire value is grounded answers. Verify tool-calling
against Perplexity's current docs before pointing a client at it.

Every provider raises the same shared exceptions
(`ChatProviderAuthError`/`ChatProviderRateLimitError`/
`ChatProviderConnectionError`/`ChatProviderError`), so `/chat`'s error
responses (500/429/502 below) look identical no matter which provider is
configured.

### Model configuration

See [Step 1](01-setup.md) for the full env var list (`CHAT_PROVIDER`,
`CHAT_MODEL`, `CHAT_MAX_TOKENS`, `CHAT_EFFORT`, `CHAT_THINKING`). The
Anthropic-specific defaults are tuned for a **deterministic
business-reporting agent**, not a creative one: modest `max_tokens`
(short business answers), no extended thinking unless explicitly turned
on, and no sampling parameters exposed (Opus 4.8 rejects non-default
`temperature`/`top_p`/`top_k` outright -- determinism here comes from
tight tool schemas and a narrow system prompt).

## The web widget

`http://127.0.0.1:8000/app/` -- a minimal static page (`web/index.html`):
type a message, or click the microphone button to speak it (Web Speech
API; the mic button hides itself in browsers that don't support it, text
input always works). Same-origin by default, so no configuration is
needed to run it locally.

## The demo dashboard

`http://127.0.0.1:8000/app/demo.html` (`web/demo.html`) -- a fuller
picture than the chat widget alone: on load it calls `POST /demo/seed`
(demo-only, not part of the client-facing API), which creates a demo
entity, classifies its chart of accounts, uploads this repo's own
`sample_data/` files, and runs a reconciliation -- then renders the
reconciliation summary, trial balance tie-out, exceptions, and a live P&L
(Sumly) as cards, with the same chat widget embedded below for asking
follow-up questions conversationally. "Reload demo data" re-runs the
reconciliation on the same seeded source (so it stays deterministic and
doesn't pile up duplicate entities on repeat loads) -- useful for showing
that a learned suppression from Step 5 actually reduces the flag count on
a subsequent run.

If the widget is deployed separately from the backend (e.g. widget on
Azure Static Web Apps, backend on Azure Container Apps -- see
[Step 10](10-deployment.md)), two things need to agree:

- `web/config.js`'s `API_BASE_URL` -- where the widget sends requests
- the backend's `ALLOWED_ORIGINS` env var -- which origins it accepts
  cross-origin requests from

This was verified end-to-end during development: the widget and backend
were run on two different local ports with `ALLOWED_ORIGINS` configured,
driven with a headless browser, and confirmed the cross-origin request
reached the server cleanly with no CORS-blocked errors (just the expected
"not configured" response, since no API key was set in that test either).

## Next

[Step 9: Security, Roles & Audit](09-security-roles-audit.md)
