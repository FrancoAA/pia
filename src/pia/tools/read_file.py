from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App

MAX_LINES = 200
MAX_LINE_LEN = 2000


class ReadFileTool:
    name = "read_file"
    description = "Read the contents of a file with line numbers, or list a directory."

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(name="path", type="string", description="Absolute or relative file/directory path.", required=True),
                ToolParam(name="offset", type="integer", description="Starting line number (0-based). Default 0.", required=False),
                ToolParam(name="limit", type="integer", description=f"Max lines to read. Default {MAX_LINES}.", required=False),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs["path"]).expanduser().resolve()
        offset: int = kwargs.get("offset", 0)
        limit: int = kwargs.get("limit", MAX_LINES)

        if not path.exists():
            return f"Error: path does not exist: {path}"

        if path.is_dir():
            return self._list_dir(path)

        mime, _ = mimetypes.guess_type(str(path))
        if mime and not mime.startswith("text") and mime != "application/json":
            size = path.stat().st_size
            return f"Binary file ({mime}), {size} bytes."

        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError as e:
            return f"Error reading file: {e}"

        total = len(lines)
        selected = lines[offset : offset + limit]

        result_lines: list[str] = []
        for i, line in enumerate(selected, start=offset + 1):
            if len(line) > MAX_LINE_LEN:
                line = line[:MAX_LINE_LEN] + "… (truncated)"
            result_lines.append(f"{i}: {line}")

        output = "\n".join(result_lines)
        if offset + limit < total:
            output += f"\n\n({total - offset - limit} more lines not shown. Use offset={offset + limit} to continue.)"

        return output or "(empty file)"

    def _list_dir(self, path: Path) -> str:
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as e:
            return f"Error listing directory: {e}"

        lines: list[str] = []
        for entry in entries[:100]:
            kind = "dir" if entry.is_dir() else "file"
            lines.append(f"  {kind}  {entry.name}")

        header = f"Directory: {path}\n"
        if len(entries) > 100:
            header += f"(showing 100 of {len(entries)} entries)\n"

        return header + "\n".join(lines)
