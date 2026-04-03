from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App


class WriteFileTool:
    name = "write_file"
    description = "Create or overwrite a file with the given content."

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(name="path", type="string", description="File path to write to.", required=True),
                ToolParam(name="content", type="string", description="Content to write.", required=True),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs["path"]).expanduser().resolve()
        content: str = kwargs["content"]

        if self.app.config.dry_run:
            return f"[dry-run] Would write {len(content)} bytes to {path}"

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            existed = path.exists()
            path.write_text(content)
            action = "Overwrote" if existed else "Created"
            return f"{action} {path} ({len(content.encode())} bytes)"
        except OSError as e:
            return f"Error writing file: {e}"
