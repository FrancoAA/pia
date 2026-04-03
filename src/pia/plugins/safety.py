from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pia.executor import is_dangerous, load_dangerous_patterns
from pia.plugins._base import Hook, PluginInfo

if TYPE_CHECKING:
    from pia.app import App


class SafetyPlugin:
    def __init__(self, app: App) -> None:
        self.app = app
        self._patterns: list[str] = []

    def info(self) -> PluginInfo:
        return PluginInfo(
            name="safety",
            description="Dangerous command detection and confirmation prompts.",
        )

    def hooks(self) -> list[Hook]:
        return [Hook.ON_INIT, Hook.BEFORE_TOOL_CALL]

    def on_on_init(self) -> None:
        self._patterns = load_dangerous_patterns(self.app.config.dangerous_file)

    def on_before_tool_call(self, tool_name: str, arguments: dict[str, Any], **kwargs: Any) -> bool | None:
        if tool_name == "run_command":
            command = arguments.get("command", "")
            return self._check_command(command)
        return None

    def _check_command(self, command: str) -> bool | None:
        """Returns True to block, None to allow."""
        if not is_dangerous(command, self._patterns):
            return None

        self.app.display.warn(f"Dangerous command detected: {command}")
        if not self.app.display.confirm("Allow this command?"):
            self.app.display.error("Command blocked.")
            return True
        return None
