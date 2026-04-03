from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App

__all__ = ["Tool", "ToolSchema", "ToolParam", "ToolRegistry"]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def all_schemas(self) -> list[dict]:
        return [t.schema().to_openai_dict() for t in self._tools.values()]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        try:
            return tool.execute(**arguments)
        except Exception as e:
            return f"Error executing {name}: {e}"


def load_builtin_tools(app: App) -> ToolRegistry:
    from pia.tools.run_command import RunCommandTool
    from pia.tools.read_file import ReadFileTool
    from pia.tools.write_file import WriteFileTool
    from pia.tools.edit_file import EditFileTool
    from pia.tools.search_files import SearchFilesTool
    from pia.tools.search_content import SearchContentTool
    from pia.tools.delegate_task import DelegateTaskTool

    registry = ToolRegistry()
    registry.register(RunCommandTool(app))
    registry.register(ReadFileTool(app))
    registry.register(WriteFileTool(app))
    registry.register(EditFileTool(app))
    registry.register(SearchFilesTool(app))
    registry.register(SearchContentTool(app))
    registry.register(DelegateTaskTool(app))
    return registry
