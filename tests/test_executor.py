"""Tests for pia.executor — dangerous command detection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pia.executor import is_dangerous, load_dangerous_patterns, DEFAULT_DANGEROUS_PATTERNS


class TestIsDangerous(unittest.TestCase):
    def test_detects_rm_rf_root(self):
        self.assertTrue(is_dangerous("rm -rf /"))

    def test_detects_rm_rf_home(self):
        self.assertTrue(is_dangerous("rm -rf ~"))

    def test_detects_rm_rf_dot(self):
        self.assertTrue(is_dangerous("rm -rf ."))

    def test_detects_mkfs(self):
        self.assertTrue(is_dangerous("mkfs /dev/sda1"))

    def test_detects_dd(self):
        self.assertTrue(is_dangerous("dd if=/dev/zero of=/dev/sda"))

    def test_detects_chmod_777(self):
        self.assertTrue(is_dangerous("chmod 777 /etc/passwd"))

    def test_detects_kill_9(self):
        self.assertTrue(is_dangerous("kill -9 1234"))

    def test_detects_sudo_rm(self):
        self.assertTrue(is_dangerous("sudo rm -rf /var"))

    def test_detects_fork_bomb(self):
        self.assertTrue(is_dangerous(":(){ :|:& };:"))

    def test_detects_reboot(self):
        self.assertTrue(is_dangerous("reboot"))

    def test_detects_shutdown(self):
        self.assertTrue(is_dangerous("shutdown -h now"))

    def test_detects_dev_write(self):
        self.assertTrue(is_dangerous("> /dev/sda"))

    def test_safe_commands_pass(self):
        safe = ["ls -la", "cat file.txt", "echo hello", "python script.py", "git status"]
        for cmd in safe:
            self.assertFalse(is_dangerous(cmd), f"Expected safe: {cmd!r}")

    def test_case_insensitive(self):
        self.assertTrue(is_dangerous("REBOOT"))
        self.assertTrue(is_dangerous("Shutdown -h now"))
        self.assertTrue(is_dangerous("RM -RF /"))

    def test_custom_patterns(self):
        custom = ["drop table", "truncate"]
        self.assertTrue(is_dangerous("DROP TABLE users", custom))
        self.assertTrue(is_dangerous("TRUNCATE logs", custom))
        self.assertFalse(is_dangerous("select * from users", custom))

    def test_with_no_patterns_uses_defaults(self):
        # When patterns is None, should use DEFAULT_DANGEROUS_PATTERNS
        self.assertTrue(is_dangerous("rm -rf /"))

    def test_empty_patterns_nothing_is_dangerous(self):
        self.assertFalse(is_dangerous("rm -rf /", []))


class TestLoadDangerousPatterns(unittest.TestCase):
    def test_defaults_without_file(self):
        patterns = load_dangerous_patterns(None)
        self.assertEqual(patterns, DEFAULT_DANGEROUS_PATTERNS)

    def test_loads_custom_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# comment line\ncustom_danger\n\nanother_pattern\n")
            f.flush()
            patterns = load_dangerous_patterns(Path(f.name))
        self.assertIn("custom_danger", patterns)
        self.assertIn("another_pattern", patterns)
        # Should also contain defaults
        self.assertIn("rm -rf /", patterns)
        # Comment should NOT be in patterns
        for p in patterns:
            self.assertFalse(p.startswith("#"))

    def test_nonexistent_file_returns_defaults(self):
        patterns = load_dangerous_patterns(Path("/nonexistent/file"))
        self.assertEqual(patterns, DEFAULT_DANGEROUS_PATTERNS)

    def test_empty_lines_are_skipped(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("\n\n  \n")
            f.flush()
            patterns = load_dangerous_patterns(Path(f.name))
        # Only defaults, no empty strings
        self.assertEqual(patterns, DEFAULT_DANGEROUS_PATTERNS)


if __name__ == "__main__":
    unittest.main()
