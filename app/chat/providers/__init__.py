"""Pluggable chat LLM provider: mirrors app.fx's pluggable FX provider
(get_fx_provider). Set CHAT_PROVIDER=anthropic (default) | openai | xai --
swapping providers is a config change, not a code change to the agent
loop, the tool definitions, or the /chat error handling.
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
    if provider != "anthropic":
        raise ValueError(
            f"Unknown CHAT_PROVIDER '{provider}' -- must be 'anthropic', 'openai', or 'xai'."
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
