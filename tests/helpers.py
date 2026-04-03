"""Shared test helpers — lightweight fakes for App and Display."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

from pia.config import Config
from pia.tools import ToolRegistry
from pia.plugins import PluginRegistry


class FakeDisplay:
    """Captures display calls for assertions without needing Rich."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []  # (level, text)
        self._confirm_answer = False

    def text(self, msg: str) -> None:
        self.messages.append(("text", msg))

    def info(self, msg: str) -> None:
        self.messages.append(("info", msg))

    def warn(self, msg: str) -> None:
        self.messages.append(("warn", msg))

    def error(self, msg: str) -> None:
        self.messages.append(("error", msg))

    def success(self, msg: str) -> None:
        self.messages.append(("success", msg))

    def muted(self, msg: str) -> None:
        self.messages.append(("muted", msg))

    def debug(self, msg: str) -> None:
        self.messages.append(("debug", msg))

    def markdown(self, msg: str) -> None:
        self.messages.append(("markdown", msg))

    def confirm(self, prompt: str) -> bool:
        return self._confirm_answer

    def usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        pass


def make_config(tmp: Path, **overrides: object) -> Config:
    """Create a Config pointing at a temporary directory."""
    return Config(
        config_dir=tmp / "config",
        data_dir=tmp / "data",
        api_key="test-key",
        **overrides,  # type: ignore[arg-type]
    )


def make_app(tmp: Path | None = None, **config_overrides: object):
    """Create a minimal App with fakes, suitable for unit tests."""
    from pia.app import App

    if tmp is None:
        tmp = Path(tempfile.mkdtemp())

    config = make_config(tmp, **config_overrides)
    config.ensure_dirs()
    display = FakeDisplay()

    return App(
        config=config,
        display=display,  # type: ignore[arg-type]
        tools=ToolRegistry(),
        plugins=PluginRegistry(),
        api=MagicMock(),
    )
# test comment
