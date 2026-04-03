"""Tests for pia.tools — ToolRegistry, ToolSchema, dispatch."""

from __future__ import annotations

import unittest
from typing import Any

from pia.tools._base import ToolSchema, ToolParam
from pia.tools import ToolRegistry


class DummyTool:
    name = "dummy"
    description = "A dummy tool for testing."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(name="input", type="string", description="Input text."),
                ToolParam(name="count", type="integer", description="Count.", required=False),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        return f"echo: {kwargs.get('input', '')} x{kwargs.get('count', 1)}"


class FailingTool:
    name = "failing"
    description = "Always raises."

    def schema(self) -> ToolSchema:
        return ToolSchema(name=self.name, description=self.description)

    def execute(self, **kwargs: Any) -> str:
        raise RuntimeError("intentional failure")


class TestToolSchema(unittest.TestCase):
    def test_to_openai_dict_structure(self):
        schema = ToolSchema(
            name="test_tool",
            description="Does things.",
            parameters=[
                ToolParam(name="path", type="string", description="File path.", required=True),
                ToolParam(name="verbose", type="boolean", description="Verbose?", required=False),
                ToolParam(name="mode", type="string", description="Mode.", enum=["fast", "slow"]),
            ],
        )
        d = schema.to_openai_dict()
        self.assertEqual(d["type"], "function")
        func = d["function"]
        self.assertEqual(func["name"], "test_tool")
        self.assertEqual(func["description"], "Does things.")
        params = func["parameters"]
        self.assertEqual(params["type"], "object")
        self.assertIn("path", params["properties"])
        self.assertIn("verbose", params["properties"])
        # Required should only have path and mode (not verbose)
        self.assertIn("path", params["required"])
        self.assertIn("mode", params["required"])
        self.assertNotIn("verbose", params["required"])
        # Enum should be present
        self.assertEqual(params["properties"]["mode"]["enum"], ["fast", "slow"])

    def test_empty_params(self):
        schema = ToolSchema(name="no_params", description="Nothing.")
        d = schema.to_openai_dict()
        self.assertEqual(d["function"]["parameters"]["properties"], {})
        self.assertEqual(d["function"]["parameters"]["required"], [])


class TestToolRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()

    def test_register_and_get(self):
        tool = DummyTool()
        self.registry.register(tool)
        self.assertIs(self.registry.get("dummy"), tool)

    def test_get_unknown_returns_none(self):
        self.assertIsNone(self.registry.get("nonexistent"))

    def test_all_returns_registered(self):
        t1 = DummyTool()
        t2 = FailingTool()
        self.registry.register(t1)
        self.registry.register(t2)
        self.assertEqual(len(self.registry.all()), 2)

    def test_all_schemas(self):
        self.registry.register(DummyTool())
        schemas = self.registry.all_schemas()
        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0]["function"]["name"], "dummy")

    def test_dispatch_success(self):
        self.registry.register(DummyTool())
        result = self.registry.dispatch("dummy", {"input": "hi", "count": 3})
        self.assertEqual(result, "echo: hi x3")

    def test_dispatch_unknown_tool(self):
        result = self.registry.dispatch("missing", {})
        self.assertIn("unknown tool", result.lower())

    def test_dispatch_catches_exceptions(self):
        self.registry.register(FailingTool())
        result = self.registry.dispatch("failing", {})
        self.assertIn("Error", result)
        self.assertIn("intentional failure", result)


if __name__ == "__main__":
    unittest.main()
