from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App

MAX_RESULTS = 100

EXCLUDED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "vendor", "dist", "build", ".next", "coverage", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


class SearchFilesTool:
    name = "search_files"
    description = "Find files matching a glob pattern in a directory."

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(name="pattern", type="string", description="Glob pattern (e.g. '*.py', '**/*.ts').", required=True),
                ToolParam(name="path", type="string", description="Directory to search in. Default: current directory.", required=False),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        pattern: str = kwargs["pattern"]
        base = Path(kwargs.get("path", ".")).expanduser().resolve()

        if not base.exists():
            return f"Error: directory not found: {base}"
        if not base.is_dir():
            return f"Error: not a directory: {base}"

        matches: list[tuple[float, Path]] = []

        for root, dirs, files in os.walk(base):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

            root_path = Path(root)
            for name in files:
                # Match against just the filename for simple patterns,
                # or the relative path for patterns with path separators
                rel = root_path / name
                rel_str = str(rel.relative_to(base))
                if "/" in pattern or "**" in pattern:
                    if fnmatch.fnmatch(rel_str, pattern):
                        mtime = (root_path / name).stat().st_mtime
                        matches.append((mtime, rel))
                else:
                    if fnmatch.fnmatch(name, pattern):
                        mtime = (root_path / name).stat().st_mtime
                        matches.append((mtime, rel))

                if len(matches) > MAX_RESULTS * 2:
                    break

        # Sort by mtime, newest first
        matches.sort(key=lambda x: x[0], reverse=True)
        matches = matches[:MAX_RESULTS]

        if not matches:
            return f"No files matching '{pattern}' found in {base}"

        lines = [str(m[1]) for m in matches]
        output = "\n".join(lines)
        if len(matches) == MAX_RESULTS:
            output += f"\n\n(results limited to {MAX_RESULTS})"
        return output
