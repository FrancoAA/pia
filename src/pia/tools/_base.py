from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolParam:
    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None
    items: dict | None = None  # for array types


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: list[ToolParam] = field(default_factory=list)

    def to_openai_dict(self) -> dict:
        props: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.items:
                prop["items"] = p.items
            props[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str

    def schema(self) -> ToolSchema: ...
    def execute(self, **kwargs: Any) -> str: ...
