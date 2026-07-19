"""Pluggable chat LLM provider: mirrors app.fx's pluggable FX provider
(get_fx_provider). Set CHAT_PROVIDER=anthropic (default) | openai | xai |
perplexity -- swapping providers is a config change, not a code change to
the agent loop, the tool definitions, or the /chat error handling.

Perplexity caveat (see docs/08-chat-agent-and-widget.md): its Sonar API is
OpenAI-compatible for the request/response wire format, which is why it
reuses OpenAICompatibleChatProvider like xAI does -- but unlike xAI,
Sonar's function/tool-calling support is not confirmed reliable. If it
doesn't honor the `tools` it's sent, a Perplexity-backed chat can answer
in prose but never actually call run_reconciliation, get_close_status,
etc. -- verify this against Perplexity's current docs before relying on
it for anything that needs real data out of this app, not just a written
answer.
"""
from __future__ import annotations

import os

from app.chat.providers.base import (
    ChatProvider,
    ChatProviderAuthError,
    ChatProviderConnectionError,
    ChatProviderError,
    ChatProviderRateLimitError,
)

XAI_BASE_URL = "https://api.x.ai/v1"
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"


def get_chat_provider() -> ChatProvider:
    provider = os.environ.get("CHAT_PROVIDER", "anthropic").strip().lower()

    if provider == "openai":
        from app.chat.providers.openai_compatible import OpenAICompatibleChatProvider

        return OpenAICompatibleChatProvider(
            api_key_env="OPENAI_API_KEY",
            base_url=None,
            default_model="gpt-4o",
            model_env="CHAT_MODEL",
        )
    if provider == "xai":
        from app.chat.providers.openai_compatible import OpenAICompatibleChatProvider

        return OpenAICompatibleChatProvider(
            api_key_env="XAI_API_KEY",
            base_url=XAI_BASE_URL,
            default_model="grok-4",
            model_env="CHAT_MODEL",
        )
    if provider == "perplexity":
        from app.chat.providers.openai_compatible import OpenAICompatibleChatProvider

        return OpenAICompatibleChatProvider(
            api_key_env="PERPLEXITY_API_KEY",
            base_url=PERPLEXITY_BASE_URL,
            default_model="sonar-pro",
            model_env="CHAT_MODEL",
        )
    if provider != "anthropic":
        raise ValueError(
            f"Unknown CHAT_PROVIDER '{provider}' -- must be 'anthropic', 'openai', 'xai', or 'perplexity'."
        )

    from app.chat.providers.anthropic_provider import AnthropicChatProvider

    return AnthropicChatProvider()


__all__ = [
    "ChatProvider",
    "ChatProviderError",
    "ChatProviderAuthError",
    "ChatProviderRateLimitError",
    "ChatProviderConnectionError",
    "get_chat_provider",
]
