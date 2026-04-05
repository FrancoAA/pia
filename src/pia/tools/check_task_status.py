from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App


class CheckTaskStatusTool:
    name = "check_task_status"
    description = (
        "Check the status of background tasks. "
        "Provide a task_id to check a specific task, or omit it to list all tasks."
    )

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(
                    name="task_id",
                    type="string",
                    description="ID of the task to check (e.g. 'task_1'). Omit to list all tasks.",
                    required=False,
                ),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        task_id: str | None = kwargs.get("task_id")
        tm = self.app.task_manager

        if task_id:
            status, detail = tm.status(task_id)
            return f"Task {task_id}: {status.value} — {detail}"

        tasks = tm.list_tasks()
        if not tasks:
            return "No background tasks."
        lines = [f"  {tid}: {status.value} — {desc}" for tid, desc, status in tasks]
        return "Background tasks:\n" + "\n".join(lines)
