"""The headless chat agent: a tool-use loop over the Claude API, using the
existing reconciliation/entity/RAG/skill code as its only tools.

Model/effort/token defaults are chosen for a *deterministic business
reporting* agent, not a creative one:
  - Model defaults to claude-opus-4-8 (override via CHAT_MODEL for cost --
    claude-sonnet-5 is a reasonable cheaper choice for this well-scoped
    tool-calling task).
  - Sampling parameters (temperature/top_p/top_k) aren't set: Opus 4.8
    rejects non-default values outright, and determinism here comes from
    tight tool schemas and a narrow system prompt, not from sampling.
  - Extended thinking is left off by default (omitting `thinking` on Opus
    4.8 runs without it) -- this agent's job is routing to tools and
    reporting their output verbatim, not open-ended reasoning. Set
    CHAT_THINKING=adaptive to turn it on for harder queries.
  - max_tokens defaults to a modest 4096: replies are short business
    answers, not long-form generation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import anthropic

from app.chat.tools import ALL_TOOLS

DEFAULT_MODEL = os.environ.get("CHAT_MODEL", "claude-opus-4-8")
DEFAULT_MAX_TOKENS = int(os.environ.get("CHAT_MAX_TOKENS", "4096"))
DEFAULT_EFFORT = os.environ.get("CHAT_EFFORT", "medium")
DEFAULT_THINKING = os.environ.get("CHAT_THINKING")  # unset, or "adaptive"

SYSTEM_PROMPT = """You are the month-end close & reconciliation assistant for Two Rivers \
Advisory clients. You help comptrollers and CFOs run bank-to-GL reconciliations, review \
exceptions, and check trial-balance tie-outs by voice or text -- no dashboard required.

Rules:
- If it's ambiguous which legal entity a request is about, call list_entities and ask \
the user to confirm before running anything.
- Report figures exactly as returned by tools. Never estimate, round beyond what a tool \
returned, or invent a number.
- When a user says an exception isn't a real issue (e.g. "that vendor always pays late, \
stop flagging it"), use record_exception_feedback so it doesn't recur -- don't just \
promise to remember it in conversation, since that memory doesn't persist.
- Keep answers short and numbers-first: a comptroller wants the figure, then the one \
relevant caveat, not a report.
"""


@dataclass
class ChatSession:
    messages: list[dict] = field(default_factory=list)


_sessions: dict[str, ChatSession] = {}


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _request_kwargs() -> dict:
    kwargs: dict = {
        "model": DEFAULT_MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "output_config": {"effort": DEFAULT_EFFORT},
    }
    if DEFAULT_THINKING:
        kwargs["thinking"] = {"type": DEFAULT_THINKING}
    return kwargs


def send_message(session_id: str, user_message: str) -> str:
    session = _sessions.setdefault(session_id, ChatSession())
    session.messages.append({"role": "user", "content": user_message})

    client = _client()
    runner = client.beta.messages.tool_runner(
        tools=ALL_TOOLS,
        messages=session.messages,
        **_request_kwargs(),
    )

    final_message = None
    for message in runner:
        final_message = message

    if final_message is None:
        return "(no response)"

    session.messages.append({"role": "assistant", "content": final_message.content})

    text_parts = [block.text for block in final_message.content if block.type == "text"]
    return "\n".join(text_parts) if text_parts else "(no text response)"


def reset_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
