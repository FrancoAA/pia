from __future__ import annotations

from pathlib import Path

DEFAULT_DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf .",
    "mkfs",
    "dd ",
    "fdisk",
    "chmod 777",
    "chown",
    "kill -9",
    "reboot",
    "shutdown",
    "mv /",
    "sudo rm",
    "> /dev/sd",
    ":(){ :|:& };:",
]


def load_dangerous_patterns(dangerous_file: Path | None = None) -> list[str]:
    patterns = list(DEFAULT_DANGEROUS_PATTERNS)
    if dangerous_file and dangerous_file.exists():
        try:
            for line in dangerous_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        except OSError:
            pass
    return patterns


def is_dangerous(command: str, patterns: list[str] | None = None) -> bool:
    if patterns is None:
        patterns = DEFAULT_DANGEROUS_PATTERNS
    cmd = command.strip().lower()
    for pattern in patterns:
        if pattern.lower() in cmd:
            return True
    return False
