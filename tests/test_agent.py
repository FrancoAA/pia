"""Tests for pia.agent — Agent abstraction."""

from __future__ import annotations

import unittest
from io import StringIO
from unittest.mock import MagicMock

from pia.agent import Agent
from pia.api import Message, ToolCall, Usage
from pia.config import Config
from pia.plugins import PluginRegistry
from pia.tools import ToolRegistry


def _make_agent(
    responses: list[Message],
    tools: ToolRegistry | None = None,
    system_prompt: str = "You are a test agent.",
    **kwargs: object,
) -> Agent:
    """Create an Agent whose API client returns canned responses."""
    config = Config(api_key="test-key", max_iterations=10)
    api = MagicMock()
    call_count = 0

    def fake_chat_loop(messages, tool_schemas, dispatch, *, hooks=None):
        nonlocal call_count
        for resp in responses:
            messages.append(resp)
        api.last_usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        return responses[-1]

    api.chat_loop = fake_chat_loop
    api.last_usage = Usage()

    return Agent(
        config=config,
        api=api,
        tools=tools or ToolRegistry(),
        plugins=PluginRegistry(),
        output=StringIO(),
        system_prompt=system_prompt,
        **kwargs,  # type: ignore[arg-type]
    )


class TestAgentRun(unittest.TestCase):
    def test_run_returns_assistant_content(self):
        resp = Message(role="assistant", content="Hello!")
        agent = _make_agent([resp])

        result = agent.run("Hi")
        self.assertEqual(result, "Hello!")

    def test_run_writes_to_output(self):
        resp = Message(role="assistant", content="output text")
        agent = _make_agent([resp])

        agent.run("prompt")
        self.assertEqual(agent.output.getvalue(), "output text")

    def test_run_reads_from_input_when_no_prompt(self):
        resp = Message(role="assistant", content="response")
        agent = _make_agent([resp])
        agent.input = StringIO("input from stream")

        result = agent.run()
        self.assertEqual(result, "response")
        # The input should have been consumed
        self.assertEqual(agent.input.read(), "")

    def test_run_with_explicit_prompt_ignores_input(self):
        resp = Message(role="assistant", content="done")
        agent = _make_agent([resp])
        agent.input = StringIO("should be ignored")

        result = agent.run("explicit prompt")
        self.assertEqual(result, "done")
        # Input stream should NOT have been consumed
        self.assertEqual(agent.input.read(), "should be ignored")

    def test_empty_response(self):
        resp = Message(role="assistant", content=None)
        agent = _make_agent([resp])

        result = agent.run("Hi")
        self.assertEqual(result, "")
        self.assertEqual(agent.output.getvalue(), "")

    def test_last_usage(self):
        resp = Message(role="assistant", content="ok")
        agent = _make_agent([resp])

        agent.run("test")
        usage = agent.last_usage
        self.assertEqual(usage.prompt_tokens, 10)
        self.assertEqual(usage.completion_tokens, 5)

    def test_system_prompt_override(self):
        resp = Message(role="assistant", content="ok")
        agent = _make_agent([resp], system_prompt="Custom system prompt")

        agent.run("test")
        self.assertEqual(agent.system_prompt, "Custom system prompt")

    def test_tools_are_passed_to_chat_loop(self):
        """Verify that tool schemas are forwarded to the API."""
        from pia.tools._base import ToolSchema, ToolParam

        class FakeTool:
            name = "greet"
            description = "Says hello"

            def schema(self):
                return ToolSchema(
                    name="greet",
                    description="Says hello",
                    parameters=[ToolParam(name="name", type="string", description="Who to greet")],
                )

            def execute(self, **kwargs):
                return f"Hello, {kwargs['name']}!"

        registry = ToolRegistry()
        registry.register(FakeTool())  # type: ignore[arg-type]

        resp = Message(role="assistant", content="Hi there!")
        agent = _make_agent([resp], tools=registry)

        result = agent.run("greet me")
        self.assertEqual(result, "Hi there!")

    def test_multiple_agents_independent_output(self):
        """Two agents with separate StringIO outputs don't interfere."""
        resp1 = Message(role="assistant", content="agent1 output")
        resp2 = Message(role="assistant", content="agent2 output")

        agent1 = _make_agent([resp1])
        agent2 = _make_agent([resp2])

        agent1.run("task1")
        agent2.run("task2")

        self.assertEqual(agent1.output.getvalue(), "agent1 output")
        self.assertEqual(agent2.output.getvalue(), "agent2 output")


class TestAgentSystemPrompt(unittest.TestCase):
    def test_dynamic_system_prompt_when_none(self):
        """When system_prompt is None, it should be built dynamically."""
        resp = Message(role="assistant", content="ok")
        config = Config(api_key="test-key", max_iterations=10)
        api = MagicMock()

        captured_messages: list[list[Message]] = []

        def fake_chat_loop(messages, tool_schemas, dispatch, *, hooks=None):
            captured_messages.append(list(messages))
            messages.append(resp)
            api.last_usage = Usage()
            return resp

        api.chat_loop = fake_chat_loop
        api.last_usage = Usage()

        agent = Agent(
            config=config,
            api=api,
            tools=ToolRegistry(),
            plugins=PluginRegistry(),
            output=StringIO(),
            system_prompt=None,  # should trigger dynamic build
        )

        agent.run("test")

        # The first message should be a system message with dynamically built content
        self.assertEqual(captured_messages[0][0].role, "system")
        self.assertIn("pia", captured_messages[0][0].content)


if __name__ == "__main__":
    unittest.main()
