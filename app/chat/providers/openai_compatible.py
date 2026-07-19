"""Chat provider for OpenAI (ChatGPT) and xAI (Grok) -- xAI's API is
OpenAI-compatible, so both are the exact same client pointed at a
different base_url/key/model, not two separate implementations.

Unlike Anthropic's `tool_runner`, the `openai` SDK has no built-in
multi-round tool-calling loop, so this hand-rolls it: call the model,
check for tool_calls, execute them via each tool's own `.call(dict)`
(reusing the same anthropic.beta_tool-wrapped functions and their
`.input_schema` as the OpenAI function-calling schema -- no second,
hand-maintained set of tool definitions), feed the results back, repeat.
"""
from __future__ import annotations

import json
import os

import openai
from openai import OpenAI

from app.chat.providers.base import (
    ChatProvider,
    ChatProviderAuthError,
    ChatProviderConnectionError,
    ChatProviderError,
    ChatProviderRateLimitError,
)

# Generous but finite -- a well-behaved conversation resolves in 1-3 rounds;
# this only guards against a model stuck calling tools in a loop.
MAX_TOOL_ROUNDS = 8


def _to_openai_tool_schema(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


class OpenAICompatibleChatProvider(ChatProvider):
    def __init__(self, api_key_env: str, base_url: str | None, default_model: str, model_env: str):
        self._api_key_env = api_key_env
        self._base_url = base_url
        self._model = os.environ.get(model_env, default_model)

    def send(self, messages: list[dict], system_prompt: str, tools: list) -> str:
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise ChatProviderAuthError(
                f"Chat agent is not configured (missing {self._api_key_env})"
            )
        client = OpenAI(api_key=api_key, base_url=self._base_url)

        tools_by_name = {t.name: t for t in tools}
        oai_tools = [_to_openai_tool_schema(t) for t in tools]
        oai_messages: list[dict] = [{"role": "system", "content": system_prompt}, *messages]

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = client.chat.completions.create(
                    model=self._model, messages=oai_messages, tools=oai_tools
                )
                message = response.choices[0].message

                if not message.tool_calls:
                    return message.content or "(no text response)"

                oai_messages.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            }
                            for tc in message.tool_calls
                        ],
                    }
                )
                for tc in message.tool_calls:
                    oai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": self._call_tool(tools_by_name, tc.function.name, tc.function.arguments),
                        }
                    )
        except openai.AuthenticationError as exc:
            raise ChatProviderAuthError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise ChatProviderRateLimitError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise ChatProviderConnectionError(str(exc)) from exc
        except openai.APIStatusError as exc:
            raise ChatProviderError(str(exc)) from exc
        except openai.OpenAIError as exc:
            raise ChatProviderAuthError(str(exc)) from exc

        return "(stopped after too many tool-call rounds without a final answer)"

    def _call_tool(self, tools_by_name: dict, name: str, arguments_json: str) -> str:
        tool = tools_by_name.get(name)
        if tool is None:
            return f"Unknown tool: {name}"
        try:
            args = json.loads(arguments_json or "{}")
            return tool.call(args)
        except Exception as exc:
            # A malformed call or a tool raising (bad args, missing entity,
            # etc.) becomes a tool result the model can react to, not a
            # crashed request -- same effect as Anthropic's tool_runner,
            # which already handles this for the other provider.
            return f"Tool error: {exc}"
