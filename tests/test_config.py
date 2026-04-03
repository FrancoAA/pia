"""Tests for pia.config — config loading hierarchy, type casting, env vars."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pia.config import Config, load_config, _cast


class TestConfigDefaults(unittest.TestCase):
    def test_default_values(self):
        cfg = Config()
        self.assertEqual(cfg.api_url, "https://openrouter.ai/api/v1")
        self.assertEqual(cfg.model, "openai/gpt-4o")
        self.assertEqual(cfg.max_tokens, 4096)
        self.assertAlmostEqual(cfg.temperature, 0.7)
        self.assertEqual(cfg.max_iterations, 100)
        self.assertFalse(cfg.dry_run)
        self.assertFalse(cfg.debug)

    def test_derived_paths(self):
        cfg = Config(config_dir=Path("/tmp/test_cfg"), data_dir=Path("/tmp/test_data"))
        self.assertEqual(cfg.config_file, Path("/tmp/test_cfg/config.toml"))
        self.assertEqual(cfg.profiles_file, Path("/tmp/test_cfg/profiles.json"))
        self.assertEqual(cfg.dangerous_file, Path("/tmp/test_cfg/dangerous_commands"))
        self.assertEqual(cfg.user_prompt_file, Path("/tmp/test_cfg/prompt.txt"))
        self.assertEqual(cfg.memory_file, Path("/tmp/test_cfg/memory.md"))
        self.assertEqual(cfg.history_dir, Path("/tmp/test_data/history"))

    def test_ensure_dirs_creates_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(
                config_dir=Path(tmp) / "cfg",
                data_dir=Path(tmp) / "data",
            )
            self.assertFalse(cfg.config_dir.exists())
            cfg.ensure_dirs()
            self.assertTrue(cfg.config_dir.exists())
            self.assertTrue(cfg.data_dir.exists())
            self.assertTrue(cfg.history_dir.exists())


class TestCast(unittest.TestCase):
    def test_bool_true_values(self):
        for val in ("1", "true", "True", "TRUE", "yes", "Yes"):
            self.assertTrue(_cast("dry_run", val), f"Expected True for {val!r}")

    def test_bool_false_values(self):
        for val in ("0", "false", "no", "anything"):
            self.assertFalse(_cast("dry_run", val), f"Expected False for {val!r}")

    def test_int_cast(self):
        self.assertEqual(_cast("max_tokens", "8192"), 8192)

    def test_float_cast(self):
        self.assertAlmostEqual(_cast("temperature", "0.5"), 0.5)

    def test_string_passthrough(self):
        self.assertEqual(_cast("api_url", "https://example.com"), "https://example.com")


class TestLoadConfigFromFile(unittest.TestCase):
    def test_config_file_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / ".config" / "pia"
            cfg_dir.mkdir(parents=True)
            (cfg_dir / "config.toml").write_text(
                'model = "anthropic/claude-3"\nmax_tokens = 2048\n'
            )
            # Point Config to our temp config dir
            original_config_file = Config(config_dir=cfg_dir).config_file
            self.assertTrue(original_config_file.exists())

            cfg = Config(config_dir=cfg_dir)
            # Simulate load_config layer 1
            import sys
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            with open(cfg.config_file, "rb") as f:
                data = tomllib.load(f)
            for key, value in data.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)

            self.assertEqual(cfg.model, "anthropic/claude-3")
            self.assertEqual(cfg.max_tokens, 2048)
            # Other defaults still intact
            self.assertAlmostEqual(cfg.temperature, 0.7)


class TestLoadConfigEnvVars(unittest.TestCase):
    def test_env_vars_override_defaults(self):
        env = {
            "PIA_API_KEY": "env-key-123",
            "PIA_MODEL": "google/gemini",
            "PIA_MAX_TOKENS": "1024",
            "PIA_TEMPERATURE": "0.3",
            "PIA_DRY_RUN": "true",
            "PIA_DEBUG": "1",
        }
        old_env = {}
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v
        try:
            cfg = load_config()
            self.assertEqual(cfg.api_key, "env-key-123")
            self.assertEqual(cfg.model, "google/gemini")
            self.assertEqual(cfg.max_tokens, 1024)
            self.assertAlmostEqual(cfg.temperature, 0.3)
            self.assertTrue(cfg.dry_run)
            self.assertTrue(cfg.debug)
        finally:
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_cli_overrides_beat_env_vars(self):
        os.environ["PIA_MODEL"] = "env-model"
        try:
            cfg = load_config(model="cli-model")
            self.assertEqual(cfg.model, "cli-model")
        finally:
            os.environ.pop("PIA_MODEL", None)

    def test_none_cli_overrides_are_ignored(self):
        cfg = load_config(model=None)
        # Should keep default, not set to None
        self.assertEqual(cfg.model, "openai/gpt-4o")


if __name__ == "__main__":
    unittest.main()
