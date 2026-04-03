"""Tests for pia.plugins.skills — skill discovery, loading, and prompt injection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pia.plugins.skills import (
    SkillsPlugin,
    _parse_frontmatter,
    _load_skill_content,
    _scan_directory,
)

from tests.helpers import make_app


def _write_skill(base: Path, dirname: str, name: str, description: str, body: str) -> Path:
    """Create a skill directory with a SKILL.md file."""
    skill_dir = base / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}"
    )
    return skill_dir


class TestFrontmatterParsing(unittest.TestCase):
    def test_parses_name_and_description(self):
        text = "---\nname: my-skill\ndescription: Does things\n---\nBody here"
        meta = _parse_frontmatter(text)
        self.assertEqual(meta["name"], "my-skill")
        self.assertEqual(meta["description"], "Does things")

    def test_returns_empty_when_no_frontmatter(self):
        meta = _parse_frontmatter("Just plain text")
        self.assertEqual(meta, {})

    def test_handles_extra_whitespace(self):
        text = "---\n  name:  spaced  \n---\nBody"
        meta = _parse_frontmatter(text)
        self.assertEqual(meta["name"], "spaced")


class TestLoadSkillContent(unittest.TestCase):
    def test_returns_body_after_frontmatter(self):
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "SKILL.md"
        f.write_text("---\nname: test\n---\nThe body content\nSecond line")
        content = _load_skill_content(f)
        self.assertEqual(content, "The body content\nSecond line")

    def test_returns_full_text_without_frontmatter(self):
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "SKILL.md"
        f.write_text("No frontmatter here")
        content = _load_skill_content(f)
        self.assertEqual(content, "No frontmatter here")


class TestScanDirectory(unittest.TestCase):
    def test_finds_skills_in_subdirectories(self):
        tmp = Path(tempfile.mkdtemp())
        _write_skill(tmp, "alpha", "alpha", "Alpha skill", "Alpha body")
        _write_skill(tmp, "beta", "beta", "Beta skill", "Beta body")

        entries = _scan_directory(tmp)
        names = {e.name for e in entries}
        self.assertEqual(names, {"alpha", "beta"})

    def test_uses_dirname_when_name_missing(self):
        tmp = Path(tempfile.mkdtemp())
        skill_dir = tmp / "fallback"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: no name\n---\nbody")

        entries = _scan_directory(tmp)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "fallback")

    def test_returns_empty_for_missing_directory(self):
        entries = _scan_directory(Path("/nonexistent/path"))
        self.assertEqual(entries, [])

    def test_skips_files_not_directories(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "not-a-dir.md").write_text("hello")
        entries = _scan_directory(tmp)
        self.assertEqual(entries, [])


class TestSkillsPlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.app = make_app(self.tmp)

    def test_discover_from_config_dir(self):
        skills_dir = self.app.config.config_dir / "skills"
        _write_skill(skills_dir, "greet", "greet", "Greeting skill", "Say hello")

        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()

        self.assertIn("greet", plugin._skills)

    def test_discover_from_data_dir(self):
        skills_dir = self.app.config.data_dir / "skills"
        _write_skill(skills_dir, "shared", "shared", "Shared skill", "Shared body")

        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()

        self.assertIn("shared", plugin._skills)

    def test_higher_priority_overrides(self):
        # data_dir (low priority)
        data_skills = self.app.config.data_dir / "skills"
        _write_skill(data_skills, "dup", "dup", "Low priority", "Low body")

        # config_dir (higher priority)
        config_skills = self.app.config.config_dir / "skills"
        _write_skill(config_skills, "dup", "dup", "High priority", "High body")

        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()

        self.assertEqual(plugin._skills["dup"].description, "High priority")

    def test_prompt_build_lists_skills(self):
        skills_dir = self.app.config.config_dir / "skills"
        _write_skill(skills_dir, "review", "review", "Code review", "Review body")

        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()

        prompt = plugin.on_prompt_build()
        self.assertIn("review", prompt)
        self.assertIn("Code review", prompt)
        self.assertIn("load_skill", prompt)

    def test_prompt_build_empty_when_no_skills(self):
        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()
        self.assertEqual(plugin.on_prompt_build(), "")

    def test_registers_load_skill_tool(self):
        skills_dir = self.app.config.config_dir / "skills"
        _write_skill(skills_dir, "test", "test", "Test", "Body")

        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()

        tool = self.app.tools.get("load_skill")
        self.assertIsNotNone(tool)

    def test_load_skill_tool_returns_content(self):
        skills_dir = self.app.config.config_dir / "skills"
        _write_skill(skills_dir, "demo", "demo", "Demo skill", "Demo instructions here")

        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()

        tool = self.app.tools.get("load_skill")
        result = tool.execute(name="demo")
        self.assertIn("Demo instructions here", result)
        self.assertIn('<skill name="demo"', result)

    def test_load_skill_tool_unknown_skill(self):
        skills_dir = self.app.config.config_dir / "skills"
        _write_skill(skills_dir, "one", "one", "One", "Body")

        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()

        tool = self.app.tools.get("load_skill")
        result = tool.execute(name="nonexistent")
        self.assertIn("Error", result)
        self.assertIn("nonexistent", result)

    def test_does_not_register_tool_when_no_skills(self):
        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()
        self.assertIsNone(self.app.tools.get("load_skill"))

    def test_cmd_skills_list(self):
        skills_dir = self.app.config.config_dir / "skills"
        _write_skill(skills_dir, "foo", "foo", "Foo skill", "Body")

        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()
        plugin.cmd_skills("list")

        texts = [msg for level, msg in self.app.display.messages if level == "text"]
        self.assertTrue(any("foo" in t for t in texts))

    def test_cmd_skills_list_empty(self):
        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()
        plugin.cmd_skills("list")

        infos = [msg for level, msg in self.app.display.messages if level == "info"]
        self.assertTrue(any("No skills" in m for m in infos))

    def test_cmd_skills_reload(self):
        plugin = SkillsPlugin(self.app)
        plugin.on_on_init()

        # Add a skill after init
        skills_dir = self.app.config.config_dir / "skills"
        _write_skill(skills_dir, "late", "late", "Late arrival", "Body")

        plugin.cmd_skills("reload")
        self.assertIn("late", plugin._skills)

        successes = [msg for level, msg in self.app.display.messages if level == "success"]
        self.assertTrue(any("1 skill" in m for m in successes))


if __name__ == "__main__":
    unittest.main()
