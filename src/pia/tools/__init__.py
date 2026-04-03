from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App

__all__ = ["Tool", "ToolSchema", "ToolParam", "ToolRegistry", "discover_tools"]

log = logging.getLogger(__name__)

# Modules that are not tool implementations
_SKIP_MODULES = {"_base"}


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


def _is_tool_class(obj: object) -> bool:
    """Return True if *obj* is a concrete class that satisfies the Tool protocol."""
    return (
        inspect.isclass(obj)
        and isinstance(obj, type)
        and hasattr(obj, "name")
        and hasattr(obj, "description")
        and callable(getattr(obj, "schema", None))
        and callable(getattr(obj, "execute", None))
        # Exclude the Protocol itself
        and obj is not Tool
    )


def _discover_builtin_tool_classes() -> list[type]:
    """Scan the ``pia.tools`` package and return all Tool classes found."""
    package = importlib.import_module("pia.tools")
    classes: list[type] = []

    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _SKIP_MODULES:
            continue
        try:
            mod = importlib.import_module(f"pia.tools.{module_info.name}")
        except Exception:
            log.warning("Failed to import tool module %s", module_info.name, exc_info=True)
            continue

        for _attr_name, obj in inspect.getmembers(mod, _is_tool_class):
            # Only include classes defined in this module (not re-exports)
            if getattr(obj, "__module__", None) == mod.__name__:
                classes.append(obj)

    return classes


def _discover_entrypoint_tool_classes() -> list[type]:
    """Load external tool classes registered via the ``pia.tools`` entry-point group."""
    classes: list[type] = []
    try:
        from importlib.metadata import entry_points
        eps = entry_points()
        # Python 3.12+ returns a SelectableGroups; older versions return a dict
        group = eps.select(group="pia.tools") if hasattr(eps, "select") else eps.get("pia.tools", [])
    except Exception:
        return classes

    for ep in group:
        try:
            cls = ep.load()
            if _is_tool_class(cls):
                classes.append(cls)
            else:
                log.warning("Entry point %s does not satisfy the Tool protocol", ep.name)
        except Exception:
            log.warning("Failed to load tool entry point %s", ep.name, exc_info=True)

    return classes


def discover_tools(app: App) -> ToolRegistry:
    """Discover and register all tools — both built-in and from entry points."""
    registry = ToolRegistry()

    for cls in _discover_builtin_tool_classes():
        try:
            tool = cls(app)
            registry.register(tool)
        except Exception:
            log.warning("Failed to instantiate tool %s", cls, exc_info=True)

    for cls in _discover_entrypoint_tool_classes():
        try:
            tool = cls(app)
            registry.register(tool)
        except Exception:
            log.warning("Failed to instantiate external tool %s", cls, exc_info=True)

    return registry


# Backward-compatible alias
load_builtin_tools = discover_tools
