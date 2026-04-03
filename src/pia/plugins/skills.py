from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pia.plugins._base import Hook, PluginInfo
from pia.tools._base import ToolParam, ToolSchema

if TYPE_CHECKING:
    from pia.app import App

log = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class SkillEntry:
    name: str
    description: str
    path: Path
    base_dir: Path


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract simple key: value pairs from YAML-style frontmatter."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta


def _load_skill_content(path: Path) -> str:
    """Return the body of a SKILL.md file (everything after the frontmatter)."""
    text = path.read_text()
    match = _FRONTMATTER_RE.match(text)
    if match:
        return text[match.end():]
    return text


def _scan_directory(directory: Path) -> list[SkillEntry]:
    """Scan a directory for subdirectories containing SKILL.md files."""
    entries: list[SkillEntry] = []
    if not directory.is_dir():
        return entries
    for child in sorted(directory.iterdir()):
        skill_file = child / "SKILL.md"
        if child.is_dir() and skill_file.is_file():
            try:
                text = skill_file.read_text()
            except OSError:
                log.warning("Failed to read %s", skill_file)
                continue
            meta = _parse_frontmatter(text)
            name = meta.get("name", child.name)
            description = meta.get("description", "")
            entries.append(SkillEntry(
                name=name,
                description=description,
                path=skill_file,
                base_dir=child,
            ))
    return entries


class _LoadSkillTool:
    """Tool that loads a skill's content into the conversation."""

    name = "load_skill"
    description = "Load a skill by name. Returns the full skill content to follow."

    def __init__(self, app: App, registry: dict[str, SkillEntry]) -> None:
        self.app = app
        self._registry = registry

    def schema(self) -> ToolSchema:
        available = list(self._registry.keys())
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(
                    name="name",
                    type="string",
                    description="Name of the skill to load.",
                    required=True,
                    enum=available or None,
                ),
            ],
        )

    def execute(self, **kwargs: Any) -> str:
        skill_name: str = kwargs["name"]
        entry = self._registry.get(skill_name)
        if entry is None:
            available = ", ".join(sorted(self._registry)) or "(none)"
            return f"Error: unknown skill '{skill_name}'. Available: {available}"

        try:
            content = _load_skill_content(entry.path)
        except OSError as exc:
            return f"Error reading skill '{skill_name}': {exc}"

        self.app.display.muted(f"  Loaded skill: {skill_name}")
        return (
            f"<skill name=\"{entry.name}\" base_dir=\"{entry.base_dir}\">\n"
            f"{content.strip()}\n"
            f"</skill>"
        )


class SkillsPlugin:
    def __init__(self, app: App) -> None:
        self.app = app
        self._skills: dict[str, SkillEntry] = {}

    def info(self) -> PluginInfo:
        return PluginInfo(
            name="skills",
            description="Discover and load skills from SKILL.md files.",
            commands=["skills", "skill"],
        )

    def hooks(self) -> list[Hook]:
        return [Hook.ON_INIT, Hook.PROMPT_BUILD]

    # -- hooks ---------------------------------------------------------------

    def on_on_init(self) -> None:
        self._discover()
        if self._skills:
            tool = _LoadSkillTool(self.app, self._skills)
            self.app.tools.register(tool)

    def on_prompt_build(self) -> str:
        if not self._skills:
            return ""
        lines = ["\n## Available skills\n"]
        lines.append(
            "Use the `load_skill` tool to load a skill's full content "
            "before following its instructions.\n"
        )
        for entry in self._skills.values():
            desc = f" - {entry.description}" if entry.description else ""
            lines.append(f"- **{entry.name}**{desc}")
        return "\n".join(lines)

    # -- commands ------------------------------------------------------------

    def cmd_skill(self, args: str) -> None:
        """Shortcut: /skill <name> is equivalent to /skills load <name>."""
        name = args.strip()
        if not name:
            self.app.display.warn("Usage: /skill <name>")
            return
        self._cmd_load(name)

    def cmd_skills(self, args: str) -> None:
        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0] if parts else "list"

        if subcmd == "list":
            self._cmd_list()
        elif subcmd == "load":
            name = parts[1] if len(parts) > 1 else ""
            self._cmd_load(name)
        elif subcmd == "reload":
            self._cmd_reload()
        else:
            self.app.display.info("Usage: /skills [list|load <name>|reload]")

    def _cmd_list(self) -> None:
        if not self._skills:
            self.app.display.info("No skills found.")
            return
        self.app.display.info("Available skills:")
        for entry in self._skills.values():
            desc = f" - {entry.description}" if entry.description else ""
            self.app.display.text(f"  {entry.name}{desc}")

    def _cmd_load(self, name: str) -> None:
        if not name:
            self.app.display.warn("Usage: /skills load <name>")
            return
        entry = self._skills.get(name)
        if entry is None:
            self.app.display.warn(f"Unknown skill: {name}")
            return
        try:
            content = _load_skill_content(entry.path)
        except OSError as exc:
            self.app.display.error(f"Failed to read skill: {exc}")
            return
        self.app.display.markdown(content)

    def _cmd_reload(self) -> None:
        self._discover()
        if self._skills:
            tool = _LoadSkillTool(self.app, self._skills)
            self.app.tools.register(tool)
        self.app.display.success(f"Reloaded {len(self._skills)} skill(s).")

    # -- discovery -----------------------------------------------------------

    def _discover(self) -> None:
        """Scan skill directories in priority order (lowest first, highest overwrites)."""
        self._skills.clear()

        dirs = self._skill_dirs()
        for directory in dirs:
            for entry in _scan_directory(directory):
                self._skills[entry.name] = entry

        if self._skills:
            log.debug("Discovered %d skill(s): %s", len(self._skills), list(self._skills))

    def _skill_dirs(self) -> list[Path]:
        """Return skill directories ordered lowest-to-highest priority."""
        return [
            self.app.config.data_dir / "skills",    # user (lowest)
            self.app.config.config_dir / "skills",   # app
            Path(os.getcwd()) / ".pia" / "skills",   # current folder (highest)
        ]
