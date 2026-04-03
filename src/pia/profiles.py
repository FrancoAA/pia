from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pia.display import Display


@dataclass
class Profile:
    name: str
    api_url: str
    api_key: str
    model: str


class ProfileManager:
    def __init__(self, profiles_file: Path) -> None:
        self._file = profiles_file
        self._profiles: dict[str, Profile] = {}
        self._active: str = ""
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text())
            self._active = data.get("active", "")
            for name, pdata in data.get("profiles", {}).items():
                self._profiles[name] = Profile(name=name, **pdata)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active": self._active,
            "profiles": {
                name: {"api_url": p.api_url, "api_key": p.api_key, "model": p.model}
                for name, p in self._profiles.items()
            },
        }
        self._file.write_text(json.dumps(data, indent=2))
        self._file.chmod(0o600)

    @property
    def active(self) -> str:
        return self._active

    def get(self, name: str) -> Profile | None:
        return self._profiles.get(name)

    def get_active(self) -> Profile | None:
        return self._profiles.get(self._active) if self._active else None

    def names(self) -> list[str]:
        return list(self._profiles.keys())

    def add(self, profile: Profile) -> None:
        self._profiles[profile.name] = profile
        if not self._active:
            self._active = profile.name
        self._save()

    def remove(self, name: str) -> bool:
        if name not in self._profiles:
            return False
        if len(self._profiles) <= 1:
            return False
        del self._profiles[name]
        if self._active == name:
            self._active = next(iter(self._profiles))
        self._save()
        return True

    def switch(self, name: str) -> Profile | None:
        if name not in self._profiles:
            return None
        self._active = name
        self._save()
        return self._profiles[name]

    def list_profiles(self, display: Display) -> None:
        if not self._profiles:
            display.info("No profiles configured.")
            return
        display.info("Profiles:")
        for name, p in self._profiles.items():
            marker = " *" if name == self._active else ""
            display.text(f"  {name}{marker} ({p.model} @ {p.api_url})")
