"""Tests for pia.plugins — PluginRegistry, hook firing, command dispatch."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from pia.plugins._base import Hook, PluginInfo
from pia.plugins import PluginRegistry
from pia.plugins.safety import SafetyPlugin
from pia.plugins.memory import MemoryPlugin

from tests.helpers import make_app


class FakePlugin:
    """Minimal test plugin that records hook calls."""

    def __init__(self, name: str = "fake", hooks_list: list[Hook] | None = None):
        self._name = name
        self._hooks = hooks_list or []
        self.calls: list[tuple[str, dict]] = []

    def info(self) -> PluginInfo:
        return PluginInfo(name=self._name, description="Fake", commands=["fakecmd"])

    def hooks(self) -> list[Hook]:
        return self._hooks


class RecordingPlugin(FakePlugin):
    """Plugin that records before_tool_call and can block."""

    def __init__(self, block: bool = False):
        super().__init__("recorder", [Hook.BEFORE_TOOL_CALL, Hook.PROMPT_BUILD])
        self.block = block

    def on_before_tool_call(self, **kwargs: Any) -> bool | None:
        self.calls.append(("before_tool_call", kwargs))
        return True if self.block else None

    def on_prompt_build(self, **kwargs: Any) -> str:
        return "## Injected by plugin"


class TestPluginRegistry(unittest.TestCase):
    def test_register_and_list(self):
        reg = PluginRegistry()
        p = FakePlugin("alpha")
        reg.register(p)
        self.assertEqual(len(reg.all()), 1)

    def test_fire_unknown_hook_returns_none(self):
        reg = PluginRegistry()
        result = reg.fire("nonexistent_hook")
        self.assertIsNone(result)

    def test_fire_calls_subscribed_handlers(self):
        reg = PluginRegistry()
        plugin = RecordingPlugin()
        reg.register(plugin)
        reg.fire("before_tool_call", tool_name="test", arguments={})
        self.assertEqual(len(plugin.calls), 1)
        self.assertEqual(plugin.calls[0][0], "before_tool_call")

    def test_fire_returns_true_when_blocked(self):
        reg = PluginRegistry()
        blocker = RecordingPlugin(block=True)
        reg.register(blocker)
        result = reg.fire("before_tool_call", tool_name="x", arguments={})
        self.assertTrue(result)

    def test_fire_returns_none_when_not_blocked(self):
        reg = PluginRegistry()
        plugin = RecordingPlugin(block=False)
        reg.register(plugin)
        result = reg.fire("before_tool_call", tool_name="x", arguments={})
        self.assertIsNone(result)

    def test_fire_prompt_concatenates(self):
        reg = PluginRegistry()
        reg.register(RecordingPlugin())
        result = reg.fire_prompt("prompt_build")
        self.assertIn("Injected by plugin", result)

    def test_fire_prompt_unknown_hook_returns_empty(self):
        reg = PluginRegistry()
        result = reg.fire_prompt("nonexistent")
        self.assertEqual(result, "")

    def test_handle_command_dispatches(self):
        reg = PluginRegistry()
        plugin = FakePlugin("test")
        plugin.cmd_fakecmd = MagicMock()
        reg.register(plugin)

        handled = reg.handle_command("fakecmd", "some args")
        self.assertTrue(handled)
        plugin.cmd_fakecmd.assert_called_once_with("some args")

    def test_handle_command_unknown_returns_false(self):
        reg = PluginRegistry()
        self.assertFalse(reg.handle_command("unknown", ""))


class TestSafetyPlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(Path(self.tmp))

    def test_allows_safe_commands(self):
        plugin = SafetyPlugin(self.app)
        plugin.on_on_init()
        result = plugin.on_before_tool_call(tool_name="run_command", arguments={"command": "ls -la"})
        self.assertIsNone(result)

    def test_blocks_dangerous_commands_when_not_confirmed(self):
        plugin = SafetyPlugin(self.app)
        plugin.on_on_init()
        # FakeDisplay.confirm returns False by default
        result = plugin.on_before_tool_call(
            tool_name="run_command", arguments={"command": "rm -rf /"}
        )
        self.assertTrue(result)

    def test_allows_dangerous_when_confirmed(self):
        self.app.display._confirm_answer = True
        plugin = SafetyPlugin(self.app)
        plugin.on_on_init()
        result = plugin.on_before_tool_call(
            tool_name="run_command", arguments={"command": "rm -rf /"}
        )
        self.assertIsNone(result)

    def test_ignores_non_run_command_tools(self):
        plugin = SafetyPlugin(self.app)
        plugin.on_on_init()
        result = plugin.on_before_tool_call(
            tool_name="write_file", arguments={"path": "/etc/passwd", "content": "hacked"}
        )
        self.assertIsNone(result)


class TestMemoryPlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(Path(self.tmp))
        self.plugin = MemoryPlugin(self.app)

    def test_prompt_build_with_no_memory(self):
        result = self.plugin.on_prompt_build()
        self.assertEqual(result, "")

    def test_add_and_prompt_build(self):
        self.plugin.cmd_memory("add The user prefers dark mode")
        result = self.plugin.on_prompt_build()
        self.assertIn("dark mode", result)
        self.assertIn("Memories", result)

    def test_add_then_remove(self):
        self.plugin.cmd_memory("add Fact one")
        self.plugin.cmd_memory("add Fact two")
        self.plugin.cmd_memory("remove Fact one")
        content = self.app.config.memory_file.read_text()
        self.assertNotIn("Fact one", content)
        self.assertIn("Fact two", content)

    def test_clear_removes_all(self):
        self.plugin.cmd_memory("add Something")
        self.plugin.cmd_memory("clear")
        self.assertEqual(self.app.config.memory_file.read_text(), "")

    def test_add_empty_warns(self):
        self.plugin.cmd_memory("add ")
        messages = [m for m in self.app.display.messages if m[0] == "warn"]
        self.assertTrue(len(messages) > 0)


if __name__ == "__main__":
    unittest.main()
