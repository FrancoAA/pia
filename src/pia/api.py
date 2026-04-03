from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from pia.config import Config


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __iadd__(self, other: Usage) -> Usage:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        return self


@dataclass
class ToolCall:
    id: str
    function_name: str
    arguments: str  # raw JSON string


@dataclass
class Message:
    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_api_dict(self) -> dict:
        d: dict = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function_name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            d["name"] = self.name
        return d

    @classmethod
    def from_api_response(cls, data: dict) -> Message:
        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    function_name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in data["tool_calls"]
            ]
        return cls(
            role=data["role"],
            content=data.get("content"),
            tool_calls=tool_calls,
        )


@dataclass
class APIClient:
    config: Config
    last_usage: Usage = field(default_factory=Usage)

    def chat(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        body: dict = {
            "model": self.config.model,
            "messages": [m.to_api_dict() for m in messages],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if tools:
            body["tools"] = tools

        with httpx.Client(timeout=300) as client:
            resp = client.post(
                f"{self.config.api_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=body,
            )

        if resp.status_code == 401:
            raise APIError("Authentication failed. Check your API key.")
        if resp.status_code == 429:
            raise APIError("Rate limited. Please try again later.")
        if resp.status_code >= 400:
            raise APIError(f"API error {resp.status_code}: {resp.text}")

        data = resp.json()
        usage_data = data.get("usage", {})
        self.last_usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        choice = data["choices"][0]["message"]
        return Message.from_api_response(choice)

    def chat_loop(
        self,
        messages: list[Message],
        tools: list[dict],
        tool_dispatch: ToolDispatch,
        *,
        hooks: HookDispatch | None = None,
    ) -> Message:
        """Agentic tool loop: call API, execute tool calls, repeat until
        text response or max_iterations reached."""
        total_usage = Usage()

        for _ in range(self.config.max_iterations):
            if hooks:
                hooks.fire("before_api_call", messages=messages)

            assistant_msg = self.chat(messages, tools or None)
            total_usage += self.last_usage

            if hooks:
                hooks.fire("after_api_call", message=assistant_msg, usage=self.last_usage)

            messages.append(assistant_msg)

            if not assistant_msg.tool_calls:
                break

            for tc in assistant_msg.tool_calls:
                args = json.loads(tc.arguments) if tc.arguments else {}

                blocked = False
                if hooks:
                    blocked = hooks.fire(
                        "before_tool_call",
                        tool_name=tc.function_name,
                        arguments=args,
                    )

                if blocked:
                    result = "Tool call was blocked."
                else:
                    result = tool_dispatch(tc.function_name, args)

                if hooks:
                    hooks.fire(
                        "on_tool_call",
                        tool_name=tc.function_name,
                        arguments=args,
                        result=result,
                    )

                messages.append(Message(
                    role="tool",
                    content=result,
                    tool_call_id=tc.id,
                    name=tc.function_name,
                ))

        self.last_usage = total_usage
        return messages[-1] if messages else Message(role="assistant", content="")


class APIError(Exception):
    pass


# Type aliases for callables passed into chat_loop
from typing import Callable, Protocol

ToolDispatch = Callable[[str, dict], str]


class HookDispatch(Protocol):
    def fire(self, hook_name: str, **kwargs: object) -> object: ...
