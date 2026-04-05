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

        from io import StringIO

        from pia.agent import Agent
        from pia.tools import ToolRegistry

        # Build subagent prompt
        user_content = task
        if context:
            user_content = f"Context:\n{context}\n\nTask:\n{task}"

        # Build a tool registry without delegate_task to prevent recursion
        sub_tools = ToolRegistry()
        for tool in self.app.tools.all():
            if tool.name != "delegate_task":
                sub_tools.register(tool)

        self.app.display.muted(f"  Delegating: {task[:80]}...")

        agent = Agent(
            config=self.app.config,
            api=self.app.api,
            tools=sub_tools,
            plugins=self.app.plugins,
            output=StringIO(),
            system_prompt=SUBAGENT_SYSTEM_PROMPT,
        )

        response = agent.run(user_content)
        return response or "(sub-agent produced no output)"
