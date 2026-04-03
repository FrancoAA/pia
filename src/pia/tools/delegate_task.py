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

        from pia.api import Message

        # Build subagent prompt
        user_content = task
        if context:
            user_content = f"Context:\n{context}\n\nTask:\n{task}"

        messages = [
            Message(role="system", content=SUBAGENT_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        # Filter out delegate_task to prevent recursion
        tools = [
            s for s in self.app.tools.all_schemas()
            if s["function"]["name"] != "delegate_task"
        ]

        self.app.display.muted(f"  Delegating: {task[:80]}...")

        result = self.app.api.chat_loop(
            messages,
            tools,
            self.app.tools.dispatch,
        )

        return result.content or "(sub-agent produced no output)"
