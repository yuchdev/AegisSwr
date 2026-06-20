"""Cross-platform symbol cache directory resolution"""
from __future__ import annotations
from typing import Optional

import os
import sys
from pathlib import Path

_ENV_OVERRIDE = "AEGIS_SYMBOL_CACHE"


def resolve_symbol_path(config_value: Optional[str]) -> Path:
    """Resolve the local symbol cache directory.

    Precedence: explicit config value → ``AEGIS_SYMBOL_CACHE`` env var →
    platform default (``%LOCALAPPDATA%\\AegisSWR\\symbols`` on Windows,
    ``~/.cache/aegis-swr/symbols`` elsewhere).
    """
    if config_value:
        return Path(config_value)
    env = os.environ.get(_ENV_OVERRIDE)
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "AegisSWR" / "symbols"
    return Path.home() / ".cache" / "aegis-swr" / "symbols"
