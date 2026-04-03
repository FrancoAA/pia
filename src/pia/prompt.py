from __future__ import annotations

import os
import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pia.app import App

BASE_PROMPT = """\
You are pia, a terminal AI agent that helps users execute and automate tasks from the console.

## Rules

- Adapt to the user's shell syntax.
- Prefer portable, cross-platform commands when possible.
- For destructive operations, prefer safer alternatives (e.g. move to trash instead of rm).
- When writing files, use the write_file or edit_file tools.
- Break complex tasks into visible steps.
- If a request is ambiguous, ask the user for clarification.
- Be concise and direct in your responses.

## Mode-specific behavior

- **Single-prompt / pipe mode**: Output EXACTLY the requested result. No greetings, no "Here is…", no markdown formatting around plain results, no follow-up suggestions.
- **Interactive mode**: You may provide context, suggestions, and follow-ups.
"""


def build_system_prompt(app: App) -> str:
    parts: list[str] = [BASE_PROMPT]

    # Environment context
    shell = os.path.basename(os.environ.get("SHELL", "bash"))
    parts.append(f"\n## Environment\n")
    parts.append(f"- Shell: {shell}")
    parts.append(f"- OS: {platform.system()} {platform.release()}")
    parts.append(f"- Working directory: {os.getcwd()}")
    parts.append(f"- Mode: {'interactive' if app.interactive else 'single-prompt'}")

    # Tool descriptions
    if app.tools.all():
        parts.append("\n## Available tools\n")
        for tool in app.tools.all():
            parts.append(f"- **{tool.name}**: {tool.description}")

    # User preferences
    if app.config.user_prompt_file.exists():
        try:
            text = app.config.user_prompt_file.read_text().strip()
            lines = [
                l for l in text.splitlines()
                if l.strip() and not l.strip().startswith("#")
            ]
            if lines:
                parts.append("\n## User preferences\n")
                parts.extend(lines)
        except OSError:
            pass

    # Plugin prompt contributions
    plugin_prompt = app.plugins.fire_prompt("prompt_build")
    if plugin_prompt:
        parts.append(plugin_prompt)

    return "\n".join(parts)
