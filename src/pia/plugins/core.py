from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from pia.plugins._base import Hook, PluginInfo

if TYPE_CHECKING:
    from pia.app import App


class CorePlugin:
    def __init__(self, app: App) -> None:
        self.app = app

    def info(self) -> PluginInfo:
        return PluginInfo(
            name="core",
            description="Core commands: help, plugins, compact, init.",
            commands=["help", "plugins", "compact"],
        )

    def hooks(self) -> list[Hook]:
        return [Hook.ON_INIT]

    def on_on_init(self) -> None:
        if not self.app.config.api_key:
            self.app.display.warn("No API key configured.")
            if sys.stdin.isatty():
                self.app.display.info("Run 'pia init' to set up your configuration.")

    def cmd_help(self, args: str) -> None:
        display = self.app.display
        display.info("Available commands:")
        display.text("  /help      - Show this help message")
        display.text("  /plugins   - List loaded plugins")
        display.text("  /compact   - Summarize conversation to save context")
        display.text("  /reset     - Clear conversation history")
        display.text("  /exit      - Exit the REPL")
        # Show plugin commands
        for plugin in self.app.plugins.all():
            info = plugin.info()
            for cmd in info.commands:
                if cmd not in ("help", "plugins", "compact"):
                    display.text(f"  /{cmd}")

    def cmd_plugins(self, args: str) -> None:
        display = self.app.display
        display.info("Loaded plugins:")
        for plugin in self.app.plugins.all():
            info = plugin.info()
            display.text(f"  {info.name} - {info.description}")

    def cmd_compact(self, args: str) -> None:
        """Summarize the conversation to reduce context size."""
        from pia.api import Message

        repl = self.app._repl
        if repl is None or len(repl.messages) < 2:
            self.app.display.warn("Nothing to compact.")
            return

        # Build a transcript of the conversation
        transcript_lines: list[str] = []
        for msg in repl.messages:
            if msg.role in ("user", "assistant") and msg.content:
                transcript_lines.append(f"{msg.role}: {msg.content}")

        transcript = "\n".join(transcript_lines)
        summary_prompt = (
            "Provide a detailed but concise summary of this conversation. "
            "Focus on information helpful for continuing the conversation.\n\n"
            f"{transcript}"
        )

        messages = [
            Message(role="system", content="You are a helpful summarizer."),
            Message(role="user", content=summary_prompt),
        ]

        self.app.display.muted("Compacting conversation...")
        with self.app.display.spinner("Summarizing..."):
            result = self.app.api.chat(messages)

        if result.content:
            repl.messages = [Message(role="assistant", content=result.content)]
            self.app.display.success("Conversation compacted.")
        else:
            self.app.display.warn("Failed to compact conversation.")
