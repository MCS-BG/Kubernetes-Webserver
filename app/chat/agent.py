"""The headless chat agent: routes a conversation to a pluggable LLM
provider (Anthropic, OpenAI/ChatGPT, or xAI/Grok -- see app/chat/providers/,
selected via CHAT_PROVIDER), using the existing reconciliation/entity/RAG/
skill/close-workflow code as its only tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.chat.providers import get_chat_provider
from app.chat.tools import ALL_TOOLS

SYSTEM_PROMPT = """You are LedgeOS, the headless close & reporting assistant for Two \
Rivers Advisory clients. You have two capabilities, both reachable in the same \
conversation: Ledge (bank-to-GL reconciliation, exception review, trial-balance tie-out) \
and Sumly (live profit & loss reporting). Help comptrollers and CFOs run either one by \
voice or text -- no dashboard required.

Rules:
- If it's ambiguous which legal entity a request is about, call list_entities and ask \
the user to confirm before running anything.
- For "why hasn't month-end closed" or any close-status question, call get_close_status \
-- it's grounded in the actual workflow state (not started / in progress / pending \
review / approved / rejected, plus any blocking critical exceptions). Never guess a \
reason that tool doesn't return.
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


def send_message(session_id: str, user_message: str) -> str:
    session = _sessions.setdefault(session_id, ChatSession())
    session.messages.append({"role": "user", "content": user_message})

    provider = get_chat_provider()
    reply = provider.send(session.messages, SYSTEM_PROMPT, ALL_TOOLS)

    session.messages.append({"role": "assistant", "content": reply})
    return reply


def reset_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
