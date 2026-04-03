"""Tests for pia.prompt — system prompt building."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from typing import Any

from pia.prompt import build_system_prompt, BASE_PROMPT
from pia.tools._base import ToolSchema, ToolParam
from pia.tools import ToolRegistry
from pia.plugins import PluginRegistry
from pia.plugins._base import Hook, PluginInfo

from tests.helpers import make_app, FakeDisplay


class StubTool:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    def schema(self) -> ToolSchema:
        return ToolSchema(name=self.name, description=self.description)

    def execute(self, **kwargs: Any) -> str:
        return ""


class PromptPlugin:
    """Plugin that contributes to the system prompt."""

    def info(self) -> PluginInfo:
        return PluginInfo(name="prompt_test", description="Test")

    def hooks(self) -> list[Hook]:
        return [Hook.PROMPT_BUILD]

    def on_prompt_build(self, **kwargs: Any) -> str:
        return "\n## Custom Section\n\nCustom content here."


class TestBuildSystemPrompt(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.app = make_app(self.tmp)

    def test_contains_base_prompt(self):
        prompt = build_system_prompt(self.app)
        self.assertIn("pia", prompt)
        self.assertIn("terminal AI agent", prompt)

    def test_contains_environment_info(self):
        prompt = build_system_prompt(self.app)
        self.assertIn("Environment", prompt)
        self.assertIn("Shell:", prompt)
        self.assertIn("OS:", prompt)
        self.assertIn("Working directory:", prompt)

    def test_contains_mode(self):
        self.app.interactive = False
        prompt = build_system_prompt(self.app)
        self.assertIn("single-prompt", prompt)

        self.app.interactive = True
        prompt = build_system_prompt(self.app)
        self.assertIn("interactive", prompt)

    def test_includes_tool_descriptions(self):
        self.app.tools.register(StubTool("my_tool", "Does amazing things"))
        prompt = build_system_prompt(self.app)
        self.assertIn("Available tools", prompt)
        self.assertIn("my_tool", prompt)
        self.assertIn("Does amazing things", prompt)

    def test_no_tools_section_when_empty(self):
        prompt = build_system_prompt(self.app)
        self.assertNotIn("Available tools", prompt)

    def test_includes_user_preferences(self):
        self.app.config.ensure_dirs()
        self.app.config.user_prompt_file.write_text(
            "# comment\nAlways use vim keybindings\nPrefer dark mode\n"
        )
        prompt = build_system_prompt(self.app)
        self.assertIn("User preferences", prompt)
        self.assertIn("vim keybindings", prompt)
        self.assertIn("dark mode", prompt)
        # Comments should be filtered out
        self.assertNotIn("# comment", prompt)

    def test_ignores_missing_user_prompt_file(self):
        prompt = build_system_prompt(self.app)
        self.assertNotIn("User preferences", prompt)

    def test_plugin_prompt_contributions(self):
        self.app.plugins.register(PromptPlugin())
        prompt = build_system_prompt(self.app)
        self.assertIn("Custom Section", prompt)
        self.assertIn("Custom content here", prompt)


if __name__ == "__main__":
    unittest.main()
