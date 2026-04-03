"""Tests for pia.api — Message serialization, Usage, chat_loop logic."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from pia.api import Message, ToolCall, Usage, APIClient, APIError
from pia.config import Config


class TestUsage(unittest.TestCase):
    def test_iadd_accumulates(self):
        a = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        b = Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
        a += b
        self.assertEqual(a.prompt_tokens, 30)
        self.assertEqual(a.completion_tokens, 15)
        self.assertEqual(a.total_tokens, 45)

    def test_default_zeros(self):
        u = Usage()
        self.assertEqual(u.prompt_tokens, 0)
        self.assertEqual(u.completion_tokens, 0)
        self.assertEqual(u.total_tokens, 0)


class TestToolCall(unittest.TestCase):
    def test_fields(self):
        tc = ToolCall(id="call_1", function_name="read_file", arguments='{"path": "/tmp"}')
        self.assertEqual(tc.id, "call_1")
        self.assertEqual(tc.function_name, "read_file")
        self.assertEqual(json.loads(tc.arguments), {"path": "/tmp"})


class TestMessage(unittest.TestCase):
    def test_to_api_dict_simple(self):
        msg = Message(role="user", content="Hello")
        d = msg.to_api_dict()
        self.assertEqual(d, {"role": "user", "content": "Hello"})

    def test_to_api_dict_with_tool_calls(self):
        tc = ToolCall(id="c1", function_name="run_command", arguments='{"command": "ls"}')
        msg = Message(role="assistant", content="Running...", tool_calls=[tc])
        d = msg.to_api_dict()
        self.assertEqual(d["role"], "assistant")
        self.assertEqual(len(d["tool_calls"]), 1)
        self.assertEqual(d["tool_calls"][0]["id"], "c1")
        self.assertEqual(d["tool_calls"][0]["type"], "function")
        self.assertEqual(d["tool_calls"][0]["function"]["name"], "run_command")

    def test_to_api_dict_tool_response(self):
        msg = Message(role="tool", content="file contents", tool_call_id="c1", name="read_file")
        d = msg.to_api_dict()
        self.assertEqual(d["role"], "tool")
        self.assertEqual(d["tool_call_id"], "c1")
        self.assertEqual(d["name"], "read_file")

    def test_to_api_dict_omits_none_fields(self):
        msg = Message(role="assistant", content="Hi")
        d = msg.to_api_dict()
        self.assertNotIn("tool_calls", d)
        self.assertNotIn("tool_call_id", d)
        self.assertNotIn("name", d)

    def test_from_api_response_text_only(self):
        data = {"role": "assistant", "content": "Hello there"}
        msg = Message.from_api_response(data)
        self.assertEqual(msg.role, "assistant")
        self.assertEqual(msg.content, "Hello there")
        self.assertIsNone(msg.tool_calls)

    def test_from_api_response_with_tool_calls(self):
        data = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_abc",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path": "/tmp/x", "content": "hi"}',
                    },
                }
            ],
        }
        msg = Message.from_api_response(data)
        self.assertIsNone(msg.content)
        self.assertEqual(len(msg.tool_calls), 1)
        self.assertEqual(msg.tool_calls[0].function_name, "write_file")
        self.assertEqual(msg.tool_calls[0].id, "call_abc")

    def test_roundtrip_serialization(self):
        """Message -> to_api_dict -> from_api_response should preserve data."""
        tc = ToolCall(id="c1", function_name="edit_file", arguments='{"path": "x"}')
        original = Message(role="assistant", content="Editing", tool_calls=[tc])
        d = original.to_api_dict()
        restored = Message.from_api_response(d)
        self.assertEqual(restored.role, original.role)
        self.assertEqual(restored.content, original.content)
        self.assertEqual(len(restored.tool_calls), 1)
        self.assertEqual(restored.tool_calls[0].function_name, "edit_file")


class TestChatLoop(unittest.TestCase):
    """Test chat_loop orchestration without making real API calls."""

    def _make_client(self, responses: list[Message]) -> APIClient:
        """Create an APIClient whose .chat() returns pre-canned responses."""
        config = Config(api_key="test", max_iterations=10)
        client = APIClient(config=config)
        call_count = 0

        def fake_chat(messages, tools=None):
            nonlocal call_count
            client.last_usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            resp = responses[call_count]
            call_count += 1
            return resp

        client.chat = fake_chat  # type: ignore[assignment]
        return client

    def test_single_text_response_no_tools(self):
        """When API returns text with no tool calls, loop exits after one iteration."""
        resp = Message(role="assistant", content="Done!")
        client = self._make_client([resp])

        messages: list[Message] = [Message(role="user", content="hello")]
        result = client.chat_loop(messages, [], lambda n, a: "")
        self.assertEqual(result.content, "Done!")
        # messages should have system + user + assistant
        self.assertEqual(len(messages), 2)

    def test_tool_call_then_text_response(self):
        """Loop should execute tool, add result, then get final text."""
        tc = ToolCall(id="c1", function_name="my_tool", arguments='{"x": 1}')
        tool_response = Message(role="assistant", content=None, tool_calls=[tc])
        final_response = Message(role="assistant", content="All done")

        client = self._make_client([tool_response, final_response])

        dispatch_calls: list[tuple] = []

        def fake_dispatch(name: str, args: dict) -> str:
            dispatch_calls.append((name, args))
            return "tool result"

        messages: list[Message] = [Message(role="user", content="do it")]
        client.chat_loop(messages, [{"type": "function"}], fake_dispatch)

        # Tool was dispatched
        self.assertEqual(len(dispatch_calls), 1)
        self.assertEqual(dispatch_calls[0], ("my_tool", {"x": 1}))

        # Messages should include tool result
        tool_msgs = [m for m in messages if m.role == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertEqual(tool_msgs[0].content, "tool result")
        self.assertEqual(tool_msgs[0].tool_call_id, "c1")

    def test_max_iterations_limits_loop(self):
        """Loop should stop after max_iterations even if tools keep being called."""
        tc = ToolCall(id="c1", function_name="infinite_tool", arguments="{}")
        # Return tool calls forever
        config = Config(api_key="test", max_iterations=3)
        client = APIClient(config=config)

        call_count = 0

        def fake_chat(messages, tools=None):
            nonlocal call_count
            client.last_usage = Usage()
            call_count += 1
            return Message(role="assistant", content=None, tool_calls=[tc])

        client.chat = fake_chat  # type: ignore[assignment]

        messages: list[Message] = [Message(role="user", content="go")]
        client.chat_loop(messages, [{}], lambda n, a: "ok")
        self.assertEqual(call_count, 3)

    def test_usage_accumulates_across_iterations(self):
        tc = ToolCall(id="c1", function_name="t", arguments="{}")
        tool_resp = Message(role="assistant", content=None, tool_calls=[tc])
        final_resp = Message(role="assistant", content="done")
        client = self._make_client([tool_resp, final_resp])

        messages: list[Message] = [Message(role="user", content="go")]
        client.chat_loop(messages, [{}], lambda n, a: "ok")

        # 2 iterations × 15 total tokens each
        self.assertEqual(client.last_usage.total_tokens, 30)

    def test_blocked_tool_call_via_hooks(self):
        """When hooks return True for before_tool_call, tool should be blocked."""
        tc = ToolCall(id="c1", function_name="dangerous", arguments="{}")
        tool_resp = Message(role="assistant", content=None, tool_calls=[tc])
        final_resp = Message(role="assistant", content="ok")
        client = self._make_client([tool_resp, final_resp])

        hooks = MagicMock()
        hooks.fire.side_effect = lambda hook_name, **kw: True if hook_name == "before_tool_call" else None

        dispatch_calls: list = []
        messages: list[Message] = [Message(role="user", content="go")]
        client.chat_loop(messages, [{}], lambda n, a: dispatch_calls.append(1) or "ok", hooks=hooks)

        # Tool dispatch should NOT have been called
        self.assertEqual(len(dispatch_calls), 0)
        # But a "blocked" tool result should have been appended
        tool_msgs = [m for m in messages if m.role == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn("blocked", tool_msgs[0].content.lower())


if __name__ == "__main__":
    unittest.main()
