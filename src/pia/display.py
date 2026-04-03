from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme

from pia.config import Config

_theme = Theme(
    {
        "info": "cyan",
        "warn": "yellow",
        "error": "bold red",
        "success": "green",
        "muted": "dim",
        "accent": "bold magenta",
    }
)


class Display:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.console = Console(theme=_theme, stderr=False)
        self.err_console = Console(theme=_theme, stderr=True)

    def markdown(self, text: str) -> None:
        self.console.print(Markdown(text))

    def text(self, text: str) -> None:
        self.console.print(text)

    def info(self, msg: str) -> None:
        self.err_console.print(f"[info]{msg}[/info]")

    def warn(self, msg: str) -> None:
        self.err_console.print(f"[warn]{msg}[/warn]")

    def error(self, msg: str) -> None:
        self.err_console.print(f"[error]{msg}[/error]")

    def success(self, msg: str) -> None:
        self.err_console.print(f"[success]{msg}[/success]")

    def muted(self, msg: str) -> None:
        self.err_console.print(f"[muted]{msg}[/muted]")

    def debug(self, msg: str) -> None:
        if self.config.debug:
            self.err_console.print(f"[muted]DEBUG: {msg}[/muted]")

    def confirm(self, prompt: str) -> bool:
        if not sys.stdin.isatty():
            return False
        try:
            answer = self.err_console.input(f"[warn]{prompt} [y/N] [/warn]")
            return answer.strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    @contextmanager
    def spinner(self, text: str = "Thinking...") -> Iterator[None]:
        with self.err_console.status(f"[muted]{text}[/muted]"):
            yield

    def usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        total = prompt_tokens + completion_tokens
        self.muted(f"tokens: {prompt_tokens} in / {completion_tokens} out / {total} total")
