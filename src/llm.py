"""
LLM adapter: OpenRouter (OpenAI-compatible) and Anthropic.

Environment variables:
  LLM_PROVIDER       openrouter (default) | anthropic
  LLM_MODEL          model ID (overrides per-provider default)
  OPENROUTER_API_KEY required when LLM_PROVIDER=openrouter
  ANTHROPIC_API_KEY  required when LLM_PROVIDER=anthropic

Tool definition format (internal, provider-agnostic):
  {"name": str, "description": str, "parameters": <JSON Schema>}

Internal message format used by agent.py:
  {"role": "user", "text": str}
  {"role": "assistant", "text": str}
  {"role": "assistant", "text": str|None, "tool_calls": [{"id", "name", "input"}]}
  {"role": "tool_results", "results": [{"id", "name", "content"}]}
"""
import json
import os
from typing import NamedTuple

# Default models: cost-optimal tool-calling models confirmed on each provider.
# google/gemini-2.5-flash: cheapest capable model on OpenRouter with Japanese support (2026-08).
# claude-haiku-4-5-20251001: cheapest Anthropic model with tool use.
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


class ToolCall(NamedTuple):
    id: str
    name: str
    input: dict


class LLMResponse(NamedTuple):
    text: str | None
    tool_calls: list  # list[ToolCall]


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools
    ]


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in tools
    ]


def _convert_messages_openai(messages: list[dict]) -> list[dict]:
    result = []
    for m in messages:
        role = m["role"]
        if role in ("user", "assistant") and "text" in m and "tool_calls" not in m:
            result.append({"role": role, "content": m["text"] or ""})
        elif role == "assistant" and "tool_calls" in m:
            result.append(
                {
                    "role": "assistant",
                    "content": m.get("text"),
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["input"], ensure_ascii=False),
                            },
                        }
                        for tc in m["tool_calls"]
                    ],
                }
            )
        elif role == "tool_results":
            for r in m["results"]:
                result.append({"role": "tool", "tool_call_id": r["id"], "content": r["content"]})
    return result


def _convert_messages_anthropic(messages: list[dict]) -> list[dict]:
    result = []
    for m in messages:
        role = m["role"]
        if role == "user" and "text" in m:
            result.append({"role": "user", "content": m["text"]})
        elif role == "assistant" and "text" in m and "tool_calls" not in m:
            result.append({"role": "assistant", "content": [{"type": "text", "text": m["text"]}]})
        elif role == "assistant" and "tool_calls" in m:
            content = []
            if m.get("text"):
                content.append({"type": "text", "text": m["text"]})
            for tc in m["tool_calls"]:
                content.append(
                    {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
                )
            result.append({"role": "assistant", "content": content})
        elif role == "tool_results":
            result.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
                        for r in m["results"]
                    ],
                }
            )
    return result


class OpenRouterClient:
    def __init__(self):
        from openai import OpenAI

        self.model = os.environ.get("LLM_MODEL", DEFAULT_OPENROUTER_MODEL)
        self._client = OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )

    def chat(self, messages: list[dict], tools: list[dict], system: str) -> LLMResponse:
        oai_messages = [{"role": "system", "content": system}] + _convert_messages_openai(messages)
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=oai_messages,
            tools=_to_openai_tools(tools),
        )
        choice = resp.choices[0]
        msg = choice.message
        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            return LLMResponse(
                text=msg.content,
                tool_calls=[
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        input=json.loads(tc.function.arguments),
                    )
                    for tc in msg.tool_calls
                ],
            )
        return LLMResponse(text=msg.content, tool_calls=[])


class AnthropicClient:
    def __init__(self):
        import anthropic

        self.model = os.environ.get("LLM_MODEL", DEFAULT_ANTHROPIC_MODEL)
        self._client = anthropic.Anthropic()

    def chat(self, messages: list[dict], tools: list[dict], system: str) -> LLMResponse:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=_convert_messages_anthropic(messages),
            tools=_to_anthropic_tools(tools),
        )
        if resp.stop_reason == "tool_use":
            tool_calls = [
                ToolCall(id=b.id, name=b.name, input=b.input)
                for b in resp.content
                if b.type == "tool_use"
            ]
            text_parts = [b.text for b in resp.content if b.type == "text"]
            return LLMResponse(text=text_parts[0] if text_parts else None, tool_calls=tool_calls)
        text_parts = [b.text for b in resp.content if b.type == "text"]
        return LLMResponse(text=text_parts[0] if text_parts else "", tool_calls=[])


def make_client() -> OpenRouterClient | AnthropicClient:
    provider = os.environ.get("LLM_PROVIDER", "openrouter").lower()
    if provider == "openrouter":
        return OpenRouterClient()
    if provider == "anthropic":
        return AnthropicClient()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Use 'openrouter' or 'anthropic'.")
