"""Pluggable chat LLM provider interface -- mirrors app.fx.base.FXRateProvider.
`app/chat/agent.py` and `app/chat/router.py` only ever depend on
`ChatProvider` and this module's exceptions, never a specific vendor SDK,
so swapping/adding an LLM backend is a new provider class, not a change to
the agent loop or the API error handling.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ChatProviderError(Exception):
    """Base for any chat-provider failure the API layer turns into a clean
    HTTP error instead of a raw 500. Provider implementations should catch
    their own SDK's exceptions and re-raise as one of the subclasses below
    (or this base class, for anything else SDK-specific)."""


class ChatProviderAuthError(ChatProviderError):
    """Missing/invalid API key, or any configuration error the SDK raises
    before making an HTTP call at all."""


class ChatProviderRateLimitError(ChatProviderError):
    """The provider is rate-limiting this key."""


class ChatProviderConnectionError(ChatProviderError):
    """Could not reach the provider's API at all (network/DNS/timeout)."""


class ChatProvider(ABC):
    @abstractmethod
    def send(self, messages: list[dict], system_prompt: str, tools: list) -> str:
        """Runs one full turn -- including any tool-call rounds -- and
        returns the final assistant text.

        `messages` is a provider-agnostic list of {"role": "user"|"assistant",
        "content": str} entries (no tool-call scaffolding persisted between
        turns -- each call's tool-call rounds are resolved internally before
        this returns). `tools` is app.chat.tools.ALL_TOOLS: a list of
        anthropic.beta_tool-wrapped functions, each exposing `.name`,
        `.description`, `.input_schema` (plain JSON Schema), and
        `.call(dict) -> str` -- providers other than Anthropic reuse these
        attributes to build their own tool-calling format rather than
        needing a second, hand-maintained set of tool schemas.
        """
        raise NotImplementedError
