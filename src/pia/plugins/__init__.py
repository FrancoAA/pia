from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pia.plugins._base import Plugin, Hook, PluginInfo

if TYPE_CHECKING:
    from pia.app import App

__all__ = ["Plugin", "Hook", "PluginInfo", "PluginRegistry"]


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._hooks: dict[Hook, list[Plugin]] = {h: [] for h in Hook}

    def register(self, plugin: Plugin) -> None:
        info = plugin.info()
        self._plugins[info.name] = plugin
        for hook in plugin.hooks():
            self._hooks[hook].append(plugin)

    def all(self) -> list[Plugin]:
        return list(self._plugins.values())

    def fire(self, hook_name: str, **kwargs: Any) -> Any:
        """Fire a hook on all subscribed plugins. Returns True if any handler
        returns True (used for blocking hooks like before_tool_call)."""
        try:
            hook = Hook(hook_name)
        except ValueError:
            return None

        method_name = f"on_{hook.value}"
        result = None
        for plugin in self._hooks[hook]:
            handler = getattr(plugin, method_name, None)
            if handler:
                ret = handler(**kwargs)
                if ret is not None:
                    result = ret
        return result

    def fire_prompt(self, hook_name: str, **kwargs: Any) -> str:
        """Fire a prompt hook and concatenate all string returns."""
        try:
            hook = Hook(hook_name)
        except ValueError:
            return ""

        method_name = f"on_{hook.value}"
        parts: list[str] = []
        for plugin in self._hooks[hook]:
            handler = getattr(plugin, method_name, None)
            if handler:
                ret = handler(**kwargs)
                if ret and isinstance(ret, str):
                    parts.append(ret)
        return "\n".join(parts)

    def handle_command(self, command: str, args: str) -> bool:
        """Try to dispatch a REPL slash-command. Returns True if handled."""
        for plugin in self._plugins.values():
            info = plugin.info()
            if command in info.commands:
                handler = getattr(plugin, f"cmd_{command}", None)
                if handler:
                    handler(args)
                    return True
        return False


def load_builtin_plugins(app: App) -> PluginRegistry:
    from pia.plugins.core import CorePlugin
    from pia.plugins.safety import SafetyPlugin
    from pia.plugins.memory import MemoryPlugin
    from pia.plugins.history import HistoryPlugin

    registry = PluginRegistry()
    registry.register(CorePlugin(app))
    registry.register(SafetyPlugin(app))
    registry.register(MemoryPlugin(app))
    registry.register(HistoryPlugin(app))
    return registry
