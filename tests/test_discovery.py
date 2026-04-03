"""Tests for dynamic tool and plugin discovery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Any

from pia.tools._base import Tool, ToolSchema, ToolParam
from pia.tools import (
    ToolRegistry,
    discover_tools,
    _is_tool_class,
    _discover_builtin_tool_classes,
)
from pia.plugins._base import Plugin, Hook, PluginInfo
from pia.plugins import (
    PluginRegistry,
    discover_plugins,
    _is_plugin_class,
    _discover_builtin_plugin_classes,
)
from tests.helpers import make_app


class SampleTool:
    name = "sample"
    description = "A sample tool."

    def __init__(self, app: Any = None) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(name=self.name, description=self.description)

    def execute(self, **kwargs: Any) -> str:
        return "ok"


class NotATool:
    """Has no name/description/schema/execute — should not be detected."""
    pass


class SamplePlugin:
    def __init__(self, app: Any = None) -> None:
        self.app = app

    def info(self) -> PluginInfo:
        return PluginInfo(name="sample", description="A sample plugin.")

    def hooks(self) -> list[Hook]:
        return []


class NotAPlugin:
    """Has no info/hooks — should not be detected."""
    pass


class TestIsToolClass(unittest.TestCase):
    def test_accepts_valid_tool(self):
        self.assertTrue(_is_tool_class(SampleTool))

    def test_rejects_non_tool(self):
        self.assertFalse(_is_tool_class(NotATool))

    def test_rejects_protocol_itself(self):
        self.assertFalse(_is_tool_class(Tool))

    def test_rejects_instances(self):
        self.assertFalse(_is_tool_class(SampleTool()))

    def test_rejects_strings(self):
        self.assertFalse(_is_tool_class("not a class"))


class TestIsPluginClass(unittest.TestCase):
    def test_accepts_valid_plugin(self):
        self.assertTrue(_is_plugin_class(SamplePlugin))

    def test_rejects_non_plugin(self):
        self.assertFalse(_is_plugin_class(NotAPlugin))

    def test_rejects_protocol_itself(self):
        self.assertFalse(_is_plugin_class(Plugin))

    def test_rejects_instances(self):
        self.assertFalse(_is_plugin_class(SamplePlugin()))


class TestDiscoverBuiltinToolClasses(unittest.TestCase):
    def test_discovers_all_builtin_tools(self):
        classes = _discover_builtin_tool_classes()
        names = {cls.name for cls in classes}
        expected = {
            "run_command", "read_file", "write_file",
            "edit_file", "search_files", "search_content",
            "delegate_task", "web_fetch",
        }
        self.assertEqual(names, expected)

    def test_all_discovered_classes_satisfy_protocol(self):
        for cls in _discover_builtin_tool_classes():
            self.assertTrue(_is_tool_class(cls), f"{cls} should satisfy Tool protocol")


class TestDiscoverBuiltinPluginClasses(unittest.TestCase):
    def test_discovers_all_builtin_plugins(self):
        classes = _discover_builtin_plugin_classes()
        # Instantiate to get names (plugins expose name via info())
        app = make_app()
        names = {cls(app).info().name for cls in classes}
        expected = {"core", "safety", "memory", "history"}
        self.assertEqual(names, expected)

    def test_all_discovered_classes_satisfy_protocol(self):
        for cls in _discover_builtin_plugin_classes():
            self.assertTrue(_is_plugin_class(cls), f"{cls} should satisfy Plugin protocol")


class TestDiscoverTools(unittest.TestCase):
    def test_returns_populated_registry(self):
        app = make_app()
        registry = discover_tools(app)
        self.assertIsInstance(registry, ToolRegistry)
        self.assertGreaterEqual(len(registry.all()), 7)

    def test_all_tools_have_schemas(self):
        app = make_app()
        registry = discover_tools(app)
        for tool in registry.all():
            schema = tool.schema()
            self.assertIsInstance(schema, ToolSchema)
            d = schema.to_openai_dict()
            self.assertEqual(d["type"], "function")

    def test_entrypoint_tools_loaded(self):
        """External entry-point tools are instantiated and registered."""
        fake_ep = MagicMock()
        fake_ep.name = "sample"
        fake_ep.load.return_value = SampleTool

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value.select.return_value = [fake_ep]
            app = make_app()
            registry = discover_tools(app)

        self.assertIsNotNone(registry.get("sample"))


class TestDiscoverPlugins(unittest.TestCase):
    def test_returns_populated_registry(self):
        app = make_app()
        registry = discover_plugins(app)
        self.assertIsInstance(registry, PluginRegistry)
        self.assertGreaterEqual(len(registry.all()), 4)

    def test_entrypoint_plugins_loaded(self):
        """External entry-point plugins are instantiated and registered."""
        fake_ep = MagicMock()
        fake_ep.name = "sample"
        fake_ep.load.return_value = SamplePlugin

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value.select.return_value = [fake_ep]
            app = make_app()
            registry = discover_plugins(app)

        names = {p.info().name for p in registry.all()}
        self.assertIn("sample", names)


class TestBackwardCompatibility(unittest.TestCase):
    def test_load_builtin_tools_alias(self):
        from pia.tools import load_builtin_tools
        self.assertIs(load_builtin_tools, discover_tools)

    def test_load_builtin_plugins_alias(self):
        from pia.plugins import load_builtin_plugins
        self.assertIs(load_builtin_plugins, discover_plugins)


if __name__ == "__main__":
    unittest.main()
