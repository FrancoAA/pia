from __future__ import annotations

import subprocess
from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App

DEFAULT_TIMEOUT = 120


class RunCommandTool:
    name = "run_command"
    description = "Execute a shell command and return its output."

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(name="command", type="string", description="The shell command to execute.", required=True),
                ToolParam(name="timeout", type="integer", description="Timeout in seconds (default 120).", required=False),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        command: str = kwargs["command"]
        timeout: int = kwargs.get("timeout", DEFAULT_TIMEOUT)

        if self.app.config.dry_run:
            return f"[dry-run] Would execute: {command}"

        self.app.display.debug(f"run_command: {command}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output:
                    output += "\n"
                output += result.stderr

            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            return output.strip() or "(no output)"

        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout} seconds."
        except Exception as e:
            return f"Error running command: {e}"
