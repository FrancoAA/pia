from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pia.tools._base import Tool, ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App


SUBAGENT_SYSTEM_PROMPT = """\
You are a focused sub-agent. Complete the task below thoroughly and concisely.
When done, provide a clear summary of what you accomplished.
You have access to tools for file operations, command execution, and search.
Do NOT delegate further sub-tasks.
"""

# Tools that sub-agents must not have access to (prevents recursion).
_EXCLUDED_TOOLS = frozenset({
    "delegate_task",
    "spawn_background_task",
    "check_task_status",
    "get_task_result",
})


def spawn_subagent(app: App, task: str, context: str = "") -> str:
    """Spawn a sub-agent in the background and return its task_id."""
    def run_agent() -> str:
        from io import StringIO

        from pia.agent import Agent
        from pia.api import APIClient
        from pia.tools import ToolRegistry

        user_content = task
        if context:
            user_content = f"Context:\n{context}\n\nTask:\n{task}"

        # Each background agent gets its own APIClient (thread safety).
        api = APIClient(config=app.config)

        sub_tools = ToolRegistry()
        for tool in app.tools.all():
            if tool.name not in _EXCLUDED_TOOLS:
                sub_tools.register(tool)

        agent = Agent(
            config=app.config,
            api=api,
            tools=sub_tools,
            plugins=app.plugins,
            output=StringIO(),
            system_prompt=SUBAGENT_SYSTEM_PROMPT,
        )

        return agent.run(user_content) or "(sub-agent produced no output)"

    return app.task_manager.spawn(task[:80], run_agent)


class SpawnBackgroundTaskTool:
    name = "spawn_background_task"
    description = (
        "Spawn a sub-agent that runs in the background. "
        "Returns a task ID immediately. Use check_task_status or "
        "get_task_result to retrieve the result later. "
        "Useful for running multiple independent explorations or tasks in parallel."
    )

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(
                    name="task",
                    type="string",
                    description="Clear, detailed description of what the sub-agent should accomplish.",
                    required=True,
                ),
                ToolParam(
                    name="context",
                    type="string",
                    description="Relevant background information for the sub-agent.",
                    required=False,
                ),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        task: str = kwargs["task"]
        context: str = kwargs.get("context", "")

        if self.app.config.dry_run:
            return f"[dry-run] Would spawn background task: {task}"

        task_id = spawn_subagent(self.app, task, context)
        description = task[:80]
        self.app.display.muted(f"  Background task spawned: {task_id} — {description}...")

        return (
            f"Background task spawned with ID: {task_id}\n"
            f"Description: {description}\n"
            "Use check_task_status to monitor progress, "
            "or get_task_result to retrieve the result."
        )
