from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App


class DelegateTaskTool:
    name = "delegate_task"
    description = "Delegate a task to a focused sub-agent with isolated context."

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(name="task", type="string", description="Clear, detailed description of what the sub-agent should accomplish.", required=True),
                ToolParam(name="context", type="string", description="Relevant background information for the sub-agent.", required=False),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        task: str = kwargs["task"]
        context: str = kwargs.get("context", "")

        if self.app.config.dry_run:
            return f"[dry-run] Would delegate task: {task}"

        from pia.tools.spawn_background_task import spawn_subagent

        self.app.display.muted(f"  Delegating: {task[:80]}...")

        # Spawn as a background task and immediately wait for the result.
        task_id = spawn_subagent(self.app, task, context)
        return self.app.task_manager.get_result(task_id)
