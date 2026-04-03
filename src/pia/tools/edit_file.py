from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App


class EditFileTool:
    name = "edit_file"
    description = "Find and replace text in a file. Fails if old_string is not found or matches multiple times (unless replace_all is true)."

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(name="path", type="string", description="File path to edit.", required=True),
                ToolParam(name="old_string", type="string", description="Text to find.", required=True),
                ToolParam(name="new_string", type="string", description="Replacement text.", required=True),
                ToolParam(name="replace_all", type="boolean", description="Replace all occurrences. Default false.", required=False),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs["path"]).expanduser().resolve()
        old_string: str = kwargs["old_string"]
        new_string: str = kwargs["new_string"]
        replace_all: bool = kwargs.get("replace_all", False)

        if not path.exists():
            return f"Error: file not found: {path}"
        if not old_string:
            return "Error: old_string cannot be empty."
        if old_string == new_string:
            return "Error: old_string and new_string are identical."

        if self.app.config.dry_run:
            return f"[dry-run] Would replace in {path}"

        try:
            content = path.read_text()
        except OSError as e:
            return f"Error reading file: {e}"

        count = content.count(old_string)
        if count == 0:
            return "Error: old_string not found in file."
        if count > 1 and not replace_all:
            return f"Error: old_string found {count} times. Set replace_all=true or provide a more specific string."

        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

        # Atomic write: write to temp file then rename
        try:
            mode = os.stat(path).st_mode
            fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            try:
                os.write(fd, new_content.encode())
                os.close(fd)
                os.chmod(tmp_path, mode)
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                os.unlink(tmp_path)
                raise
        except OSError as e:
            return f"Error writing file: {e}"

        replaced = count if replace_all else 1
        return f"Replaced {replaced} occurrence(s) in {path}"
