"""Tests for file-based tools — read_file, write_file, edit_file, search_files.

All tests use real filesystem operations in temporary directories.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_app

from pia.tools.read_file import ReadFileTool
from pia.tools.write_file import WriteFileTool
from pia.tools.edit_file import EditFileTool
from pia.tools.search_files import SearchFilesTool


class TestReadFileTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(Path(self.tmp))
        self.tool = ReadFileTool(self.app)

    def test_read_simple_file(self):
        p = Path(self.tmp) / "hello.txt"
        p.write_text("line one\nline two\nline three\n")
        result = self.tool.execute(path=str(p))
        self.assertIn("1: line one", result)
        self.assertIn("2: line two", result)
        self.assertIn("3: line three", result)

    def test_read_with_offset_and_limit(self):
        p = Path(self.tmp) / "lines.txt"
        p.write_text("\n".join(f"line {i}" for i in range(1, 11)))
        result = self.tool.execute(path=str(p), offset=3, limit=2)
        self.assertIn("4: line 4", result)
        self.assertIn("5: line 5", result)
        self.assertNotIn("line 3", result)
        self.assertNotIn("line 6", result)

    def test_read_nonexistent(self):
        result = self.tool.execute(path="/nonexistent/file.txt")
        self.assertIn("Error", result)

    def test_read_directory_lists_entries(self):
        subdir = Path(self.tmp) / "subdir"
        subdir.mkdir()
        (Path(self.tmp) / "a.txt").write_text("a")
        result = self.tool.execute(path=self.tmp)
        self.assertIn("dir", result)
        self.assertIn("subdir", result)
        self.assertIn("file", result)
        self.assertIn("a.txt", result)

    def test_read_empty_file(self):
        p = Path(self.tmp) / "empty.txt"
        p.write_text("")
        result = self.tool.execute(path=str(p))
        self.assertEqual(result, "(empty file)")

    def test_truncation_indicator(self):
        p = Path(self.tmp) / "long.txt"
        p.write_text("\n".join(f"line {i}" for i in range(500)))
        result = self.tool.execute(path=str(p), limit=10)
        self.assertIn("more lines not shown", result)

    def test_long_lines_are_truncated(self):
        p = Path(self.tmp) / "wide.txt"
        p.write_text("x" * 3000)
        result = self.tool.execute(path=str(p))
        self.assertIn("truncated", result)


class TestWriteFileTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(Path(self.tmp))
        self.tool = WriteFileTool(self.app)

    def test_creates_new_file(self):
        p = Path(self.tmp) / "new.txt"
        result = self.tool.execute(path=str(p), content="hello world")
        self.assertIn("Created", result)
        self.assertEqual(p.read_text(), "hello world")

    def test_overwrites_existing_file(self):
        p = Path(self.tmp) / "existing.txt"
        p.write_text("old content")
        result = self.tool.execute(path=str(p), content="new content")
        self.assertIn("Overwrote", result)
        self.assertEqual(p.read_text(), "new content")

    def test_creates_parent_directories(self):
        p = Path(self.tmp) / "deep" / "nested" / "file.txt"
        self.tool.execute(path=str(p), content="nested!")
        self.assertTrue(p.exists())
        self.assertEqual(p.read_text(), "nested!")

    def test_dry_run_does_not_write(self):
        app = make_app(Path(self.tmp), dry_run=True)
        tool = WriteFileTool(app)
        p = Path(self.tmp) / "dryrun.txt"
        result = tool.execute(path=str(p), content="should not appear")
        self.assertIn("dry-run", result)
        self.assertFalse(p.exists())

    def test_reports_byte_count(self):
        p = Path(self.tmp) / "bytes.txt"
        result = self.tool.execute(path=str(p), content="abc")
        self.assertIn("3 bytes", result)


class TestEditFileTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(Path(self.tmp))
        self.tool = EditFileTool(self.app)

    def _write(self, name: str, content: str) -> Path:
        p = Path(self.tmp) / name
        p.write_text(content)
        return p

    def test_single_replacement(self):
        p = self._write("a.txt", "hello world")
        result = self.tool.execute(path=str(p), old_string="hello", new_string="goodbye")
        self.assertIn("Replaced 1", result)
        self.assertEqual(p.read_text(), "goodbye world")

    def test_replace_all(self):
        p = self._write("b.txt", "aaa bbb aaa")
        result = self.tool.execute(path=str(p), old_string="aaa", new_string="ccc", replace_all=True)
        self.assertIn("Replaced 2", result)
        self.assertEqual(p.read_text(), "ccc bbb ccc")

    def test_ambiguous_match_without_replace_all(self):
        p = self._write("c.txt", "foo bar foo")
        result = self.tool.execute(path=str(p), old_string="foo", new_string="baz")
        self.assertIn("found 2 times", result)
        # File should be unchanged
        self.assertEqual(p.read_text(), "foo bar foo")

    def test_old_string_not_found(self):
        p = self._write("d.txt", "hello world")
        result = self.tool.execute(path=str(p), old_string="missing", new_string="x")
        self.assertIn("not found", result)

    def test_old_equals_new_rejected(self):
        p = self._write("e.txt", "same")
        result = self.tool.execute(path=str(p), old_string="same", new_string="same")
        self.assertIn("identical", result)

    def test_empty_old_string_rejected(self):
        p = self._write("f.txt", "content")
        result = self.tool.execute(path=str(p), old_string="", new_string="x")
        self.assertIn("empty", result)

    def test_nonexistent_file(self):
        result = self.tool.execute(path="/nonexistent", old_string="x", new_string="y")
        self.assertIn("not found", result.lower())

    def test_preserves_file_permissions(self):
        p = self._write("perm.txt", "old content")
        os.chmod(p, 0o755)
        self.tool.execute(path=str(p), old_string="old", new_string="new")
        mode = os.stat(p).st_mode & 0o777
        self.assertEqual(mode, 0o755)

    def test_dry_run_does_not_modify(self):
        app = make_app(Path(self.tmp), dry_run=True)
        tool = EditFileTool(app)
        p = self._write("dry.txt", "original")
        result = tool.execute(path=str(p), old_string="original", new_string="changed")
        self.assertIn("dry-run", result)
        self.assertEqual(p.read_text(), "original")


class TestSearchFilesTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(Path(self.tmp))
        self.tool = SearchFilesTool(self.app)
        # Create test file structure
        (Path(self.tmp) / "a.py").write_text("python")
        (Path(self.tmp) / "b.py").write_text("python")
        (Path(self.tmp) / "c.txt").write_text("text")
        sub = Path(self.tmp) / "sub"
        sub.mkdir()
        (sub / "d.py").write_text("python")

    def test_glob_py_files(self):
        result = self.tool.execute(pattern="*.py", path=self.tmp)
        self.assertIn("a.py", result)
        self.assertIn("b.py", result)
        self.assertNotIn("c.txt", result)

    def test_recursive_glob(self):
        result = self.tool.execute(pattern="**/*.py", path=self.tmp)
        self.assertIn("d.py", result)

    def test_no_matches(self):
        result = self.tool.execute(pattern="*.rs", path=self.tmp)
        self.assertIn("No files", result)

    def test_nonexistent_directory(self):
        result = self.tool.execute(pattern="*.py", path="/nonexistent")
        self.assertIn("Error", result)

    def test_excludes_pycache(self):
        pycache = Path(self.tmp) / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.py").write_text("cached")
        result = self.tool.execute(pattern="*.py", path=self.tmp)
        self.assertNotIn("cached.py", result)


if __name__ == "__main__":
    unittest.main()
