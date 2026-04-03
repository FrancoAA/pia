from __future__ import annotations

import shutil
import subprocess
from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App

MAX_RESULTS = 100
MAX_LINE_LEN = 2000

EXCLUDED_DIRS = [
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "vendor", "dist", "build", ".next", "coverage",
]


class SearchContentTool:
    name = "search_content"
    description = "Search file contents for a regex pattern using ripgrep (or grep fallback)."

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(name="pattern", type="string", description="Regex pattern to search for.", required=True),
                ToolParam(name="path", type="string", description="Directory to search in. Default: current directory.", required=False),
                ToolParam(name="include", type="string", description="File glob filter (e.g. '*.py', '*.{js,ts}').", required=False),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        pattern: str = kwargs["pattern"]
        path: str = kwargs.get("path", ".")
        include: str | None = kwargs.get("include")

        if shutil.which("rg"):
            return self._search_rg(pattern, path, include)
        return self._search_grep(pattern, path, include)

    def _search_rg(self, pattern: str, path: str, include: str | None) -> str:
        cmd = ["rg", "--no-heading", "-n", "--max-count", str(MAX_RESULTS)]
        for d in EXCLUDED_DIRS:
            cmd.extend(["--glob", f"!{d}"])
        if include:
            cmd.extend(["--glob", include])
        cmd.extend([pattern, path])
        return self._run(cmd)

    def _search_grep(self, pattern: str, path: str, include: str | None) -> str:
        cmd = ["grep", "-rn", "--color=never"]
        for d in EXCLUDED_DIRS:
            cmd.extend(["--exclude-dir", d])
        if include:
            cmd.extend(["--include", include])
        cmd.extend([pattern, path])
        return self._run(cmd)

    def _run(self, cmd: list[str]) -> str:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return "Search timed out after 30 seconds."
        except FileNotFoundError:
            return "Error: search tool not found."

        if result.returncode not in (0, 1):
            return f"Search error: {result.stderr.strip()}"

        if not result.stdout.strip():
            return "No matches found."

        lines = result.stdout.strip().splitlines()
        truncated = False
        if len(lines) > MAX_RESULTS:
            lines = lines[:MAX_RESULTS]
            truncated = True

        output_lines: list[str] = []
        for line in lines:
            if len(line) > MAX_LINE_LEN:
                line = line[:MAX_LINE_LEN] + "… (truncated)"
            output_lines.append(line)

        output = "\n".join(output_lines)
        if truncated:
            output += f"\n\n(results limited to {MAX_RESULTS})"
        return output
