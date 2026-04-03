from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


@dataclass
class Config:
    api_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    model: str = "openai/gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.7
    max_iterations: int = 100
    dry_run: bool = False
    debug: bool = False
    config_dir: Path = field(default_factory=lambda: _xdg_config_home() / "pia")
    data_dir: Path = field(default_factory=lambda: _xdg_data_home() / "pia")

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def profiles_file(self) -> Path:
        return self.config_dir / "profiles.json"

    @property
    def dangerous_file(self) -> Path:
        return self.config_dir / "dangerous_commands"

    @property
    def user_prompt_file(self) -> Path:
        return self.config_dir / "prompt.txt"

    @property
    def memory_file(self) -> Path:
        return self.config_dir / "memory.md"

    @property
    def history_dir(self) -> Path:
        return self.data_dir / "history"

    def ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)


ENV_PREFIX = "PIA_"

_ENV_MAP: dict[str, str] = {
    "PIA_API_URL": "api_url",
    "PIA_API_KEY": "api_key",
    "PIA_MODEL": "model",
    "PIA_MAX_TOKENS": "max_tokens",
    "PIA_TEMPERATURE": "temperature",
    "PIA_MAX_ITERATIONS": "max_iterations",
    "PIA_DRY_RUN": "dry_run",
    "PIA_DEBUG": "debug",
}

_INT_FIELDS = {"max_tokens", "max_iterations"}
_FLOAT_FIELDS = {"temperature"}
_BOOL_FIELDS = {"dry_run", "debug"}


def _cast(key: str, value: str) -> str | int | float | bool:
    if key in _BOOL_FIELDS:
        return value.lower() in ("1", "true", "yes")
    if key in _INT_FIELDS:
        return int(value)
    if key in _FLOAT_FIELDS:
        return float(value)
    return value


def load_config(**cli_overrides: object) -> Config:
    """Load config: CLI overrides → env vars → config file → defaults."""
    cfg = Config()

    # Layer 1: config file
    if cfg.config_file.exists():
        with open(cfg.config_file, "rb") as f:
            data = tomllib.load(f)
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)

    # Layer 2: env vars
    for env_key, attr in _ENV_MAP.items():
        value = os.environ.get(env_key)
        if value is not None:
            setattr(cfg, attr, _cast(attr, value))

    # Layer 3: CLI overrides (highest priority)
    for key, value in cli_overrides.items():
        if value is not None and hasattr(cfg, key):
            setattr(cfg, key, value)

    return cfg
