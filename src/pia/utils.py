from __future__ import annotations

import os


def debug_enabled() -> bool:
    return os.environ.get("PIA_DEBUG", "").lower() in ("1", "true", "yes")
