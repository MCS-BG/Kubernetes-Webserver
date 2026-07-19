"""Anthropic implementation -- a thin wrapper over `tool_runner`, which
already handles multi-round tool calls internally, unlike the OpenAI-
compatible provider which has to hand-roll that loop (see
openai_compatible.py).

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

import anthropic

from app.chat.providers.base import (
    ChatProvider,
    ChatProviderAuthError,
    ChatProviderConnectionError,
    ChatProviderError,
    ChatProviderRateLimitError,
)

DEFAULT_MODEL = os.environ.get("CHAT_MODEL", "claude-opus-4-8")
DEFAULT_MAX_TOKENS = int(os.environ.get("CHAT_MAX_TOKENS", "4096"))
DEFAULT_EFFORT = os.environ.get("CHAT_EFFORT", "medium")
DEFAULT_THINKING = os.environ.get("CHAT_THINKING")  # unset, or "adaptive"


class AnthropicChatProvider(ChatProvider):
    def send(self, messages: list[dict], system_prompt: str, tools: list) -> str:
        kwargs: dict = {
            "model": DEFAULT_MODEL,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "system": system_prompt,
            "output_config": {"effort": DEFAULT_EFFORT},
        }
        if DEFAULT_THINKING:
            kwargs["thinking"] = {"type": DEFAULT_THINKING}

        try:
            client = anthropic.Anthropic()
            runner = client.beta.messages.tool_runner(tools=tools, messages=messages, **kwargs)
            final_message = None
            for message in runner:
                final_message = message
        except anthropic.AuthenticationError as exc:
            raise ChatProviderAuthError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise ChatProviderRateLimitError(str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise ChatProviderConnectionError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise ChatProviderError(f"Claude API error: {exc.message}") from exc
        except (anthropic.AnthropicError, TypeError) as exc:
            # Covers configuration errors the SDK raises before any HTTP
            # call -- e.g. no ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / auth
            # profile resolvable, which surfaces as a bare TypeError, not an
            # APIStatusError.
            raise ChatProviderAuthError(str(exc)) from exc

        if final_message is None:
            return "(no response)"
        text_parts = [block.text for block in final_message.content if block.type == "text"]
        return "\n".join(text_parts) if text_parts else "(no text response)"
