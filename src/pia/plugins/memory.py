from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from pia.plugins._base import Hook, PluginInfo

if TYPE_CHECKING:
    from pia.app import App


class MemoryPlugin:
    def __init__(self, app: App) -> None:
        self.app = app

    def info(self) -> PluginInfo:
        return PluginInfo(
            name="memory",
            description="Persistent cross-session memory.",
            commands=["memory"],
        )

    def hooks(self) -> list[Hook]:
        return [Hook.PROMPT_BUILD]

    def on_prompt_build(self) -> str:
        path = self.app.config.memory_file
        if not path.exists():
            return ""
        try:
            content = path.read_text().strip()
        except OSError:
            return ""
        if not content:
            return ""
        return f"\n## Memories\n\nThese are facts you saved from previous conversations:\n\n{content}\n"

    def cmd_memory(self, args: str) -> None:
        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0] if parts else "show"
        rest = parts[1] if len(parts) > 1 else ""

        if subcmd == "show":
            self._show()
        elif subcmd == "add":
            self._add(rest)
        elif subcmd == "remove":
            self._remove(rest)
        elif subcmd == "clear":
            self._clear()
        elif subcmd == "path":
            self.app.display.text(str(self.app.config.memory_file))
        else:
            self.app.display.info("Usage: /memory [show|add|remove|clear|path]")

    def _show(self) -> None:
        path = self.app.config.memory_file
        if not path.exists() or not path.read_text().strip():
            self.app.display.info("No memories stored.")
            return
        self.app.display.markdown(path.read_text())

    def _add(self, content: str) -> None:
        if not content:
            self.app.display.warn("Usage: /memory add <fact>")
            return
        path = self.app.config.memory_file
        self.app.config.ensure_dirs()
        with open(path, "a") as f:
            f.write(f"- [{date.today()}] {content}\n")
        self.app.display.success("Memory saved.")

    def _remove(self, content: str) -> None:
        if not content:
            self.app.display.warn("Usage: /memory remove <text>")
            return
        path = self.app.config.memory_file
        if not path.exists():
            self.app.display.warn("No memories to remove.")
            return
        lines = path.read_text().splitlines()
        new_lines = [l for l in lines if content not in l]
        removed = len(lines) - len(new_lines)
        if removed == 0:
            self.app.display.warn("No matching memories found.")
            return
        path.write_text("\n".join(new_lines) + "\n" if new_lines else "")
        self.app.display.success(f"Removed {removed} memory(ies).")

    def _clear(self) -> None:
        path = self.app.config.memory_file
        if path.exists():
            path.write_text("")
        self.app.display.success("All memories cleared.")
