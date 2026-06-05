"""Debug backend factory (platform-detected, engine-selected)"""
from __future__ import annotations

import subprocess
import sys
from functools import lru_cache

from aegis_swr.backends.base import DebugBackend
from aegis_swr.backends.debug.cdb_worker import CdbBackend
from aegis_swr.backends.debug.gdb_worker import GdbBackend
from aegis_swr.backends.debug.lldb_worker import LldbBackend
from aegis_swr.backends.debug.windbg_js_worker import WinDbgJSBackend
from aegis_swr.core.exceptions import PlatformNotSupportedError
from aegis_swr.config.settings import DebugSettings

__all__ = [
    "CdbBackend",
    "GdbBackend",
    "LldbBackend",
    "WinDbgJSBackend",
    "create_debug_backend",
]


@lru_cache(maxsize=1)
def _windbg_js_available() -> bool:
    """Return True when cdb.exe loads JsProvider.dll successfully.

    Probes by running ``cdb.exe -version`` and checking for the
    ``JsProvider`` marker in the output. The result is cached after the
    first call so the probe subprocess runs at most once per process.
    Never raises — returns False on any failure.
    """
    try:
        result = subprocess.run(
            ["cdb.exe", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        return "JsProvider" in combined
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def create_debug_backend(
    settings: DebugSettings,
    platform: str | None = None,
) -> DebugBackend:
    """Construct the debug backend for the current (or given) platform.

    On Windows the engine is selected by ``settings.engine``:
    - ``"auto"``       — prefer WinDbgJSBackend if available, else CdbBackend.
    - ``"windbg_js"``  — always WinDbgJSBackend.
    - ``"cdb"``        — always CdbBackend.

    ``platform`` accepts a ``sys.platform`` string; it defaults to the running
    platform and exists primarily so tests can select a backend deterministically.
    """
    key = platform if platform is not None else sys.platform

    if key == "win32":
        engine = getattr(settings, "engine", "auto")
        if engine == "windbg_js":
            return WinDbgJSBackend(settings)
        if engine == "auto" and _windbg_js_available():
            return WinDbgJSBackend(settings)
        return CdbBackend(settings)

    if key == "linux":
        return GdbBackend(settings)
    if key == "darwin":
        return LldbBackend(settings)

    raise PlatformNotSupportedError(f"No debug backend for platform {key!r}")
