from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam
from pia.task_manager import TaskStatus

if TYPE_CHECKING:
    from pia.app import App


class GetTaskResultTool:
    name = "get_task_result"
    description = (
        "Retrieve the result of a completed background task. "
        "Set wait=true to block until the task finishes (with optional timeout)."
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
                    description="ID of the task to retrieve (e.g. 'task_1').",
                    required=True,
                ),
                ToolParam(
                    name="wait",
                    type="boolean",
                    description="If true, block until the task completes. Default: false.",
                    required=False,
                ),
                ToolParam(
                    name="timeout",
                    type="number",
                    description="Max seconds to wait when wait=true. Default: 30.",
                    required=False,
                ),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        task_id: str = kwargs["task_id"]
        wait: bool = kwargs.get("wait", False)
        timeout: float = kwargs.get("timeout", 30.0)
        tm = self.app.task_manager

        if wait:
            return tm.get_result(task_id, timeout=timeout)

        status, _ = tm.status(task_id)
        if status == TaskStatus.RUNNING:
            return (
                f"Task {task_id} is still running. "
                "Use wait=true to block until it completes, or check back later."
            )
        return tm.get_result(task_id)
