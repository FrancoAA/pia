from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pia.api import APIClient
from pia.config import Config
from pia.display import Display
from pia.plugins import PluginRegistry
from pia.tools import ToolRegistry

if TYPE_CHECKING:
    from pia.repl import REPL


@dataclass
class App:
    config: Config
    display: Display
    tools: ToolRegistry
    plugins: PluginRegistry
    api: APIClient
    interactive: bool = False
    _repl: REPL | None = field(default=None, repr=False)
