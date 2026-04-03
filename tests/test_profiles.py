"""Tests for pia.profiles — ProfileManager CRUD and persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pia.profiles import ProfileManager, Profile
from tests.helpers import FakeDisplay


class TestProfileManager(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.profiles_file = self.tmp / "profiles.json"

    def _manager(self) -> ProfileManager:
        return ProfileManager(self.profiles_file)

    def _profile(self, name: str = "test") -> Profile:
        return Profile(
            name=name,
            api_url="https://api.example.com",
            api_key="key-123",
            model="gpt-4",
        )

    def test_empty_initially(self):
        mgr = self._manager()
        self.assertEqual(mgr.names(), [])
        self.assertIsNone(mgr.get_active())

    def test_add_sets_first_as_active(self):
        mgr = self._manager()
        mgr.add(self._profile("alpha"))
        self.assertEqual(mgr.active, "alpha")
        self.assertIsNotNone(mgr.get_active())
        self.assertEqual(mgr.get_active().name, "alpha")

    def test_add_second_does_not_change_active(self):
        mgr = self._manager()
        mgr.add(self._profile("alpha"))
        mgr.add(self._profile("beta"))
        self.assertEqual(mgr.active, "alpha")

    def test_switch(self):
        mgr = self._manager()
        mgr.add(self._profile("a"))
        mgr.add(self._profile("b"))
        result = mgr.switch("b")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "b")
        self.assertEqual(mgr.active, "b")

    def test_switch_nonexistent(self):
        mgr = self._manager()
        result = mgr.switch("ghost")
        self.assertIsNone(result)

    def test_remove(self):
        mgr = self._manager()
        mgr.add(self._profile("a"))
        mgr.add(self._profile("b"))
        self.assertTrue(mgr.remove("a"))
        self.assertIsNone(mgr.get("a"))
        self.assertEqual(mgr.active, "b")

    def test_cannot_remove_last_profile(self):
        mgr = self._manager()
        mgr.add(self._profile("only"))
        self.assertFalse(mgr.remove("only"))
        self.assertEqual(len(mgr.names()), 1)

    def test_remove_nonexistent(self):
        mgr = self._manager()
        self.assertFalse(mgr.remove("ghost"))

    def test_persistence_across_instances(self):
        mgr1 = self._manager()
        mgr1.add(self._profile("saved"))
        mgr1.add(self._profile("other"))

        mgr2 = self._manager()  # Fresh load from disk
        self.assertEqual(mgr2.names(), ["saved", "other"])
        self.assertEqual(mgr2.active, "saved")
        p = mgr2.get("saved")
        self.assertEqual(p.api_key, "key-123")

    def test_file_permissions(self):
        mgr = self._manager()
        mgr.add(self._profile("secure"))
        mode = self.profiles_file.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_corrupted_file_handled_gracefully(self):
        self.profiles_file.write_text("not valid json{{{")
        mgr = self._manager()
        self.assertEqual(mgr.names(), [])

    def test_get_returns_profile(self):
        mgr = self._manager()
        mgr.add(self._profile("x"))
        p = mgr.get("x")
        self.assertIsNotNone(p)
        self.assertEqual(p.model, "gpt-4")

    def test_get_nonexistent_returns_none(self):
        mgr = self._manager()
        self.assertIsNone(mgr.get("nope"))


if __name__ == "__main__":
    unittest.main()
