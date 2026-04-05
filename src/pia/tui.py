"""Textual TUI for pia — Claude Code inspired interactive interface."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Collapsible,
    Input,
    Label,
    Markdown,
    Static,
)

from pia.agent import Agent
from pia.api import APIError, Message
from pia.prompt import build_system_prompt

if TYPE_CHECKING:
    from pia.app import App as PiaApp


CSS_PATH = Path(__file__).with_suffix(".tcss")


class PiaTUI(App):
    """Main Textual application for pia."""

    TITLE = "pia"
    CSS_PATH = CSS_PATH
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear", "Clear", show=True),
    ]

    def __init__(self, pia_app: PiaApp) -> None:
        super().__init__()
        self.pia_app = pia_app
        self.messages: list[Message] = []
        self._cancel = Event()

    # ── Layout ──────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        config = self.pia_app.config
        version = self._version()

        # Header
        with Horizontal(id="header-bar"):
            yield Label(f" pia v{version}", id="header-title")
            yield Label(f"{config.model} ", id="header-model")

        # Main conversation area
        yield VerticalScroll(id="conversation")

        # Thinking indicator
        yield Label(" Thinking...", id="thinking-indicator")

        # Input area
        with Vertical(id="input-area"):
            yield Label("> Ask anything...", id="prompt-label")
            yield Input(
                placeholder="Type a message (Enter to send, /help for commands)",
                id="user-input",
            )

        # Footer
        with Horizontal(id="footer-bar"):
            yield Label("", id="footer-usage")
            yield Label("ctrl+c quit | ctrl+l clear", id="footer-help")

    def on_mount(self) -> None:
        self.pia_app.plugins.fire("on_init")
        self._append_system(
            f"pia v{self._version()} — model: {self.pia_app.config.model}"
        )
        self._append_system("Type /help for commands, /exit to quit.")
        self.query_one("#user-input", Input).focus()

    # ── Input handling ──────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        event.input.value = ""

        if text.startswith("/"):
            self._handle_command(text)
            return

        self._process_message(text)

    # ── Slash commands ──────────────────────────────────────────

    def _handle_command(self, user_input: str) -> None:
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("exit", "quit"):
            self.exit()
            return
        if cmd == "reset":
            self.messages = []
            self.query_one("#conversation", VerticalScroll).remove_children()
            self._append_system("Conversation reset.")
            return
        if cmd == "clear":
            self.query_one("#conversation", VerticalScroll).remove_children()
            return

        if not self.pia_app.plugins.handle_command(cmd, args):
            self._append_error(f"Unknown command: /{cmd}")

    # ── Message processing ──────────────────────────────────────

    def _process_message(self, user_input: str) -> None:
        self.pia_app.plugins.fire("on_user_message", content=user_input)
        self.messages.append(Message(role="user", content=user_input))

        # Show user message in conversation
        self._append_user_message(user_input)

        # Show thinking indicator
        self._set_thinking(True)

        # Disable input while processing
        inp = self.query_one("#user-input", Input)
        inp.disabled = True

        # Run agent in background worker
        self._run_agent(user_input)

    @work(thread=True)
    def _run_agent(self, user_input: str) -> None:
        """Run the agent in a background thread."""
        tool_calls_log: list[dict] = []

        # Create a custom hook wrapper to capture tool calls
        original_fire = self.pia_app.plugins.fire

        def capturing_fire(hook_name: str, **kwargs: object) -> object:
            if hook_name == "on_tool_call":
                tool_calls_log.append({
                    "tool_name": kwargs.get("tool_name", ""),
                    "arguments": kwargs.get("arguments", {}),
                    "result": kwargs.get("result", ""),
                })
                # Update UI from the worker thread
                self.call_from_thread(
                    self._append_tool_call,
                    str(kwargs.get("tool_name", "")),
                    kwargs.get("arguments", {}),
                    str(kwargs.get("result", "")),
                )
            return original_fire(hook_name, **kwargs)

        self.pia_app.plugins.fire = capturing_fire  # type: ignore[assignment]

        try:
            agent = Agent(
                config=self.pia_app.config,
                api=self.pia_app.api,
                tools=self.pia_app.tools,
                plugins=self.pia_app.plugins,
                output=StringIO(),
                system_prompt=build_system_prompt(self.pia_app),
                interactive=True,
            )

            response = agent.run(user_input)
            usage = agent.last_usage

            self.call_from_thread(self._on_agent_done, response, usage, None)

        except APIError as e:
            self.call_from_thread(self._on_agent_done, "", None, str(e))
        except KeyboardInterrupt:
            self.call_from_thread(self._on_agent_done, "", None, "(interrupted)")
        finally:
            self.pia_app.plugins.fire = original_fire  # type: ignore[assignment]

    def _on_agent_done(
        self,
        response: str,
        usage: object | None,
        error: str | None,
    ) -> None:
        """Called on the main thread when the agent finishes."""
        self._set_thinking(False)

        if error:
            self._append_error(error)
        elif response:
            self._append_assistant_message(response)
            self.messages.append(Message(role="assistant", content=response))
            self.pia_app.plugins.fire("on_assistant_message", content=response)

        # Update footer with usage
        if usage is not None:
            pt = getattr(usage, "prompt_tokens", 0)
            ct = getattr(usage, "completion_tokens", 0)
            total = pt + ct
            footer = self.query_one("#footer-usage", Label)
            footer.update(f" tokens: {pt} in / {ct} out / {total} total")

        # Re-enable input
        inp = self.query_one("#user-input", Input)
        inp.disabled = False
        inp.focus()

        # Scroll to bottom
        conv = self.query_one("#conversation", VerticalScroll)
        conv.scroll_end(animate=False)

    # ── UI helpers ──────────────────────────────────────────────

    def _append_user_message(self, text: str) -> None:
        conv = self.query_one("#conversation", VerticalScroll)
        block = Vertical(
            Label("  You", classes="user-label"),
            Static(text, classes="message-content"),
            classes="message-block",
        )
        conv.mount(block)
        conv.scroll_end(animate=False)

    def _append_assistant_message(self, text: str) -> None:
        conv = self.query_one("#conversation", VerticalScroll)
        block = Vertical(
            Label("  Assistant", classes="assistant-label"),
            Markdown(text, classes="message-content"),
            classes="message-block",
        )
        conv.mount(block)
        conv.scroll_end(animate=False)

    def _append_tool_call(
        self, tool_name: str, arguments: object, result: str,
    ) -> None:
        conv = self.query_one("#conversation", VerticalScroll)

        args_str = ""
        if isinstance(arguments, dict):
            args_str = json.dumps(arguments, indent=2)
        elif arguments:
            args_str = str(arguments)

        # Truncate long results
        display_result = result
        if len(display_result) > 2000:
            display_result = display_result[:2000] + "\n... (truncated)"

        title = f"  {tool_name}"
        collapsible = Collapsible(
            Static(
                f"Args:\n{args_str}\n\nResult:\n{display_result}",
                classes="tool-result",
            ),
            title=title,
            collapsed=True,
            classes="tool-collapsible",
        )

        group = Vertical(collapsible, classes="tool-call-group")
        conv.mount(group)
        conv.scroll_end(animate=False)

    def _append_system(self, text: str) -> None:
        conv = self.query_one("#conversation", VerticalScroll)
        conv.mount(Static(text, classes="system-message"))
        conv.scroll_end(animate=False)

    def _append_error(self, text: str) -> None:
        conv = self.query_one("#conversation", VerticalScroll)
        conv.mount(Static(f" {text}", classes="error-message"))
        conv.scroll_end(animate=False)

    def _set_thinking(self, visible: bool) -> None:
        indicator = self.query_one("#thinking-indicator", Label)
        if visible:
            indicator.add_class("visible")
        else:
            indicator.remove_class("visible")

    # ── Actions ─────────────────────────────────────────────────

    def action_clear(self) -> None:
        self.query_one("#conversation", VerticalScroll).remove_children()

    def action_quit(self) -> None:
        self.pia_app.task_manager.shutdown()
        self.pia_app.plugins.fire("on_shutdown")
        self.exit()

    # ── Utilities ───────────────────────────────────────────────

    def _version(self) -> str:
        from pia import __version__
        return __version__
