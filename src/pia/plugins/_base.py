from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class Hook(str, Enum):
    ON_INIT = "on_init"
    ON_SHUTDOWN = "on_shutdown"
    BEFORE_API_CALL = "before_api_call"
    AFTER_API_CALL = "after_api_call"
    BEFORE_TOOL_CALL = "before_tool_call"
    ON_TOOL_CALL = "on_tool_call"
    PROMPT_BUILD = "prompt_build"
    ON_USER_MESSAGE = "on_user_message"
    ON_ASSISTANT_MESSAGE = "on_assistant_message"


@dataclass
class PluginInfo:
    name: str
    description: str
    commands: list[str] = field(default_factory=list)


@runtime_checkable
class Plugin(Protocol):
    def info(self) -> PluginInfo: ...
    def hooks(self) -> list[Hook]: ...
