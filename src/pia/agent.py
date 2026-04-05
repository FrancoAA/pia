"""Agent — composable unit that reads input, runs the agentic loop, and writes output."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from io import StringIO
from typing import TextIO

from pia.api import APIClient, APIError, Message, Usage
from pia.config import Config
from pia.plugins import PluginRegistry
from pia.prompt import build_system_prompt
from pia.tools import ToolRegistry


@dataclass
class Agent:
    """A composable agentic unit with explicit I/O and tool boundaries.

    Parameters
    ----------
    config:
        Runtime configuration (model, API key, etc.).
    api:
        The API client used to talk to the LLM.
    tools:
        Registry of tools available to this agent.
    plugins:
        Registry of plugins (hooks) for this agent.
    input:
        Where the agent reads user input from (defaults to stdin).
    output:
        Where the agent writes final responses to (defaults to stdout).
    system_prompt:
        Optional override for the system prompt.  When *None* the prompt is
        built dynamically via :func:`build_system_prompt`.
    interactive:
        Whether the agent is running in interactive (REPL) mode.
    """

    config: Config
    api: APIClient
    tools: ToolRegistry
    plugins: PluginRegistry
    input: TextIO = field(default_factory=lambda: sys.stdin)
    output: TextIO = field(default_factory=lambda: sys.stdout)
    system_prompt: str | None = None
    interactive: bool = False

    # ---- public API --------------------------------------------------------

    def run(self, prompt: str | None = None) -> str:
        """Execute a single agentic turn.

        If *prompt* is given it is used directly; otherwise the agent reads
        from ``self.input``.  The final assistant response is written to
        ``self.output`` and also returned as a string.
        """
        if prompt is None:
            prompt = self.input.read()

        system = self._resolve_system_prompt()
        tools = self.tools.all_schemas()

        messages = [
            Message(role="system", content=system),
            Message(role="user", content=prompt),
        ]

        self.plugins.fire("before_api_call", messages=messages)

        result = self.api.chat_loop(
            messages,
            tools,
            self.tools.dispatch,
            hooks=self.plugins,
        )

        # Extract the last assistant text from the conversation
        response = ""
        for msg in reversed(messages):
            if msg.role == "assistant" and msg.content:
                response = msg.content
                break

        self.output.write(response)
        return response

    @property
    def last_usage(self) -> Usage:
        return self.api.last_usage

    # ---- internals ---------------------------------------------------------

    def _resolve_system_prompt(self) -> str:
        if self.system_prompt is not None:
            return self.system_prompt

        # Build dynamically — requires a lightweight App-shaped object
        from pia.app import App

        app = App(
            config=self.config,
            display=_NullDisplay(),  # type: ignore[arg-type]
            tools=self.tools,
            plugins=self.plugins,
            api=self.api,
            interactive=self.interactive,
        )
        return build_system_prompt(app)


class _NullDisplay:
    """Minimal stub so build_system_prompt can access app.interactive."""

    def __getattr__(self, name: str) -> object:
        return lambda *a, **kw: None
