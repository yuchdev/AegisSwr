"""Public API for the code-intelligence harness package.

Re-exports the payload-free, leaf-module exception types so callers can
``from aegis_swr.harness import HarnessConfigError`` without a full module path -
mirroring ``from aegis_swr.openclaude import OpenClaudeConfigError``.

``HarnessSettings`` (subtasks 01/02) and the composition root (Task 10.0) are
deliberately **not** re-exported here yet: those modules land in later iterations
and pull in ``pydantic`` / backend clients, which must stay behind their
submodules and be constructed at the ``app.py`` composition root. Only the
``typing``-only exception hierarchy is safe to surface at package-import time.
"""

from __future__ import annotations

from aegis_swr.harness.exceptions import HarnessConfigError, HarnessUnavailableError

__all__ = [
    "HarnessConfigError",
    "HarnessUnavailableError",
]
