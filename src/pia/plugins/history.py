from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pia.plugins._base import Hook, PluginInfo

if TYPE_CHECKING:
    from pia.app import App


class HistoryPlugin:
    def __init__(self, app: App) -> None:
        self.app = app
        self._session_file: Path | None = None

    def info(self) -> PluginInfo:
        return PluginInfo(
            name="history",
            description="Session history tracking.",
            commands=["history"],
        )

    def hooks(self) -> list[Hook]:
        return [
            Hook.ON_INIT,
            Hook.ON_SHUTDOWN,
            Hook.ON_USER_MESSAGE,
            Hook.ON_ASSISTANT_MESSAGE,
            Hook.PROMPT_BUILD,
        ]

    def on_on_init(self) -> None:
        self.app.config.ensure_dirs()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._session_file = self.app.config.history_dir / f"{ts}.jsonl"

    def on_on_shutdown(self) -> None:
        # Remove empty session files
        if self._session_file and self._session_file.exists():
            if self._session_file.stat().st_size == 0:
                self._session_file.unlink()

    def on_on_user_message(self, content: str, **kwargs: Any) -> None:
        self._log("user", content)

    def on_on_assistant_message(self, content: str, **kwargs: Any) -> None:
        self._log("assistant", content)

    def on_prompt_build(self) -> str:
        """Inject recent history summaries into the prompt."""
        sessions = self._recent_sessions(2)
        if not sessions:
            return ""

        parts = ["\n## Recent session history\n"]
        for session_path in sessions:
            entries = self._read_session(session_path)
            user_msgs = [e["content"][:120] for e in entries if e["role"] == "user"][:3]
            if user_msgs:
                ts = session_path.stem.replace("_", " ")
                parts.append(f"Session {ts}:")
                for msg in user_msgs:
                    parts.append(f"  - {msg}")
        return "\n".join(parts)

    def _log(self, role: str, content: str) -> None:
        if not self._session_file or not content:
            return
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with open(self._session_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def _recent_sessions(self, count: int) -> list[Path]:
        """Get the most recent session files, excluding current."""
        history_dir = self.app.config.history_dir
        if not history_dir.exists():
            return []
        files = sorted(history_dir.glob("*.jsonl"), reverse=True)
        # Skip current session
        if self._session_file and self._session_file in files:
            files.remove(self._session_file)
        return files[:count]

    def _read_session(self, path: Path) -> list[dict]:
        entries: list[dict] = []
        try:
            for line in path.read_text().splitlines():
                if line.strip():
                    entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            pass
        return entries

    def cmd_history(self, args: str) -> None:
        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0] if parts else "list"

        if subcmd == "list":
            self._list_sessions()
        elif subcmd == "resume":
            session = parts[1] if len(parts) > 1 else ""
            self._resume_session(session)
        elif subcmd == "clear":
            self._clear_sessions()
        else:
            self.app.display.info("Usage: /history [list|resume <session>|clear]")

    def _list_sessions(self) -> None:
        history_dir = self.app.config.history_dir
        if not history_dir.exists():
            self.app.display.info("No session history.")
            return
        files = sorted(history_dir.glob("*.jsonl"), reverse=True)
        if not files:
            self.app.display.info("No session history.")
            return
        self.app.display.info("Session history:")
        for f in files[:20]:
            entries = self._read_session(f)
            count = len(entries)
            marker = " (current)" if f == self._session_file else ""
            self.app.display.text(f"  {f.stem} ({count} messages){marker}")

    def _resume_session(self, session_name: str) -> None:
        if not session_name:
            self.app.display.warn("Usage: /history resume <session-name>")
            return

        from pia.api import Message

        history_dir = self.app.config.history_dir
        candidates = list(history_dir.glob(f"{session_name}*.jsonl"))
        if not candidates:
            self.app.display.warn(f"Session not found: {session_name}")
            return

        session_path = candidates[0]
        entries = self._read_session(session_path)

        repl = self.app._repl
        if repl is None:
            self.app.display.warn("Resume is only available in REPL mode.")
            return

        repl.messages = [
            Message(role=e["role"], content=e["content"])
            for e in entries
            if e["role"] in ("user", "assistant")
        ]
        self.app.display.success(f"Resumed session with {len(repl.messages)} messages.")

    def _clear_sessions(self) -> None:
        history_dir = self.app.config.history_dir
        if not history_dir.exists():
            return
        count = 0
        for f in history_dir.glob("*.jsonl"):
            if f != self._session_file:
                f.unlink()
                count += 1
        self.app.display.success(f"Cleared {count} session(s).")
