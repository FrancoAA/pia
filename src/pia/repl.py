from __future__ import annotations

import readline
import signal
from typing import TYPE_CHECKING

from pia.agent import Agent
from pia.api import APIError, Message
from pia.prompt import build_system_prompt

if TYPE_CHECKING:
    from pia.app import App


class REPL:
    def __init__(self, app: App) -> None:
        self.app = app
        self.messages: list[Message] = []
        self._running = False

    def run(self) -> None:
        self.app._repl = self
        self.app.interactive = True
        self._running = True

        display = self.app.display
        display.info(f"pia v{self._version()} — model: {self.app.config.model}")
        display.muted("Type /help for commands, /exit to quit.\n")

        original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle_sigint)

        try:
            while self._running:
                try:
                    user_input = self._read_input()
                except EOFError:
                    break

                if not user_input:
                    continue

                # Handle slash commands
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                self._process_message(user_input)

        finally:
            signal.signal(signal.SIGINT, original_sigint)
            self.app.plugins.fire("on_shutdown")
            self.app._repl = None

    def _read_input(self) -> str:
        lines: list[str] = []
        prompt = "pia> "
        while True:
            line = input(prompt)
            if line.endswith("\\"):
                lines.append(line[:-1])
                prompt = "...  "
            else:
                lines.append(line)
                break
        return "\n".join(lines).strip()

    def _handle_command(self, user_input: str) -> None:
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("exit", "quit"):
            self._running = False
            return
        if cmd == "reset":
            self.messages = []
            self.app.display.success("Conversation reset.")
            return

        if not self.app.plugins.handle_command(cmd, args):
            self.app.display.warn(f"Unknown command: /{cmd}")

    def _process_message(self, user_input: str) -> None:
        display = self.app.display

        # Fire user message hook
        self.app.plugins.fire("on_user_message", content=user_input)

        # Add user message
        self.messages.append(Message(role="user", content=user_input))

        from io import StringIO

        agent = Agent(
            config=self.app.config,
            api=self.app.api,
            tools=self.app.tools,
            plugins=self.app.plugins,
            output=StringIO(),
            system_prompt=build_system_prompt(self.app),
            interactive=True,
        )

        try:
            with display.spinner():
                response = agent.run(user_input)

            if response:
                display.text("")
                display.markdown(response)
                display.text("")

                # Keep conversation in sync — add only the final assistant response
                self.messages.append(Message(role="assistant", content=response))

                # Fire assistant message hook
                self.app.plugins.fire("on_assistant_message", content=response)

            # Show usage
            usage = agent.last_usage
            display.usage(usage.prompt_tokens, usage.completion_tokens)

        except APIError as e:
            display.error(str(e))
        except KeyboardInterrupt:
            display.text("\n")
            display.muted("(interrupted)")

    def _handle_sigint(self, signum: int, frame: object) -> None:
        print()  # newline after ^C

    def _version(self) -> str:
        from pia import __version__
        return __version__
