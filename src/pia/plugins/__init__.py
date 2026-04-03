from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Any, TYPE_CHECKING

from pia.plugins._base import Plugin, Hook, PluginInfo

if TYPE_CHECKING:
    from pia.app import App

__all__ = ["Plugin", "Hook", "PluginInfo", "PluginRegistry", "discover_plugins"]

log = logging.getLogger(__name__)

# Modules that are not plugin implementations
_SKIP_MODULES = {"_base"}


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


def _is_plugin_class(obj: object) -> bool:
    """Return True if *obj* is a concrete class that satisfies the Plugin protocol."""
    return (
        inspect.isclass(obj)
        and isinstance(obj, type)
        and callable(getattr(obj, "info", None))
        and callable(getattr(obj, "hooks", None))
        # Exclude the Protocol itself
        and obj is not Plugin
    )


def _discover_builtin_plugin_classes() -> list[type]:
    """Scan the ``pia.plugins`` package and return all Plugin classes found."""
    package = importlib.import_module("pia.plugins")
    classes: list[type] = []

    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _SKIP_MODULES:
            continue
        try:
            mod = importlib.import_module(f"pia.plugins.{module_info.name}")
        except Exception:
            log.warning("Failed to import plugin module %s", module_info.name, exc_info=True)
            continue

        for _attr_name, obj in inspect.getmembers(mod, _is_plugin_class):
            if getattr(obj, "__module__", None) == mod.__name__:
                classes.append(obj)

    return classes


def _discover_entrypoint_plugin_classes() -> list[type]:
    """Load external plugin classes registered via the ``pia.plugins`` entry-point group."""
    classes: list[type] = []
    try:
        from importlib.metadata import entry_points
        eps = entry_points()
        group = eps.select(group="pia.plugins") if hasattr(eps, "select") else eps.get("pia.plugins", [])
    except Exception:
        return classes

    for ep in group:
        try:
            cls = ep.load()
            if _is_plugin_class(cls):
                classes.append(cls)
            else:
                log.warning("Entry point %s does not satisfy the Plugin protocol", ep.name)
        except Exception:
            log.warning("Failed to load plugin entry point %s", ep.name, exc_info=True)

    return classes


def discover_plugins(app: App) -> PluginRegistry:
    """Discover and register all plugins — both built-in and from entry points."""
    registry = PluginRegistry()

    for cls in _discover_builtin_plugin_classes():
        try:
            plugin = cls(app)
            registry.register(plugin)
        except Exception:
            log.warning("Failed to instantiate plugin %s", cls, exc_info=True)

    for cls in _discover_entrypoint_plugin_classes():
        try:
            plugin = cls(app)
            registry.register(plugin)
        except Exception:
            log.warning("Failed to instantiate external plugin %s", cls, exc_info=True)

    return registry


# Backward-compatible alias
load_builtin_plugins = discover_plugins
