"""Chat provider selection (CHAT_PROVIDER=anthropic|openai|xai) and the
OpenAI-compatible provider's hand-rolled tool-call loop -- mocked, no real
network call to any LLM API (none of the three keys are available in this
environment). Anthropic's own tool_runner loop is exercised for real, live,
via tests/test_chat_tools.py's direct .func() calls -- this file covers the
provider-selection/routing layer added on top of it, and the loop that has
no SDK-provided equivalent for OpenAI/xAI.
"""
from __future__ import annotations

import pytest

from app.chat.providers import (
    ChatProviderAuthError,
    XAI_BASE_URL,
    get_chat_provider,
)
from app.chat.providers.anthropic_provider import AnthropicChatProvider
from app.chat.providers.openai_compatible import OpenAICompatibleChatProvider


def test_get_chat_provider_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("CHAT_PROVIDER", raising=False)
    assert isinstance(get_chat_provider(), AnthropicChatProvider)


def test_get_chat_provider_selects_openai(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    provider = get_chat_provider()
    assert isinstance(provider, OpenAICompatibleChatProvider)
    assert provider._api_key_env == "OPENAI_API_KEY"
    assert provider._base_url is None


def test_get_chat_provider_selects_xai(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "xai")
    provider = get_chat_provider()
    assert isinstance(provider, OpenAICompatibleChatProvider)
    assert provider._api_key_env == "XAI_API_KEY"
    assert provider._base_url == XAI_BASE_URL


def test_get_chat_provider_case_insensitive(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "OpenAI")
    assert isinstance(get_chat_provider(), OpenAICompatibleChatProvider)


def test_get_chat_provider_rejects_unknown(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="Unknown CHAT_PROVIDER"):
        get_chat_provider()


def test_openai_provider_missing_api_key_raises_auth_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAICompatibleChatProvider(
        api_key_env="OPENAI_API_KEY", base_url=None, default_model="gpt-4o", model_env="CHAT_MODEL"
    )
    with pytest.raises(ChatProviderAuthError):
        provider.send(messages=[{"role": "user", "content": "hi"}], system_prompt="sys", tools=[])


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


def test_openai_compatible_provider_runs_tool_call_then_final_answer(monkeypatch):
    """Simulates the model calling list_entities, getting the tool's real
    output back, then answering -- proves the hand-rolled loop actually
    wires tool_calls -> tool.call(...) -> a "tool" role message -> a second
    model call, exactly like Anthropic's tool_runner does internally."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")

    from app.chat import tools as chat_tools
    from app.entities import registry as entity_registry

    entity_registry.add(name="Provider Test Co", base_currency="USD", description="")

    tool_call_response = _FakeResponse(
        _FakeMessage(
            content=None,
            tool_calls=[_FakeToolCall("call_1", "list_entities", "{}")],
        )
    )
    final_response = _FakeResponse(_FakeMessage(content="There is one entity: Provider Test Co."))

    created_calls = []

    class _FakeCompletions:
        def create(self, **kwargs):
            created_calls.append(kwargs)
            return tool_call_response if len(created_calls) == 1 else final_response

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(
        "app.chat.providers.openai_compatible.OpenAI", lambda api_key, base_url: _FakeClient()
    )

    provider = OpenAICompatibleChatProvider(
        api_key_env="OPENAI_API_KEY", base_url=None, default_model="gpt-4o", model_env="CHAT_MODEL"
    )
    reply = provider.send(
        messages=[{"role": "user", "content": "list entities"}],
        system_prompt="sys",
        tools=[chat_tools.list_entities],
    )

    assert reply == "There is one entity: Provider Test Co."
    assert len(created_calls) == 2

    # Second call's message list must include the tool's real result.
    second_call_messages = created_calls[1]["messages"]
    tool_messages = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert "Provider Test Co" in tool_messages[0]["content"]
    assert tool_messages[0]["tool_call_id"] == "call_1"
