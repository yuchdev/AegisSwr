#!/usr/bin/env python3
"""Stop hook - gate the end of a session on a green test suite.

Runs the unit suite (fast, no external services) the same way CI does. If it
fails, the hook exits 2 so Claude is told to fix the regression before it can
finish. To avoid infinite loops Claude Code suppresses this hook when the stop
was itself triggered by a prior stop-hook block (``stop_hook_active``).

Skip the gate for a known-WIP session by exporting ``AEGIS_SKIP_TESTS=1``.
"""

from __future__ import annotations

import os
import subprocess

from _common import REPO_ROOT, allow, append_log, block, read_event


def main() -> None:
    event = read_event()
    if event.get("stop_hook_active"):
        allow()
    if os.environ.get("AEGIS_SKIP_TESTS") == "1":
        append_log("tests.log", "SKIPPED (AEGIS_SKIP_TESTS=1)")
        allow()

    # --override-ini=addopts= clears the pyproject.toml addopts that inject
    # coverage flags; -p no:cov disables pytest-cov even if installed.
    # This keeps the gate fast and dependency-free.
    base_args = ["tests/unit/", "-q", "--override-ini=addopts=", "-p", "no:cov"]
    cmd = ["poetry", "run", "pytest", *base_args]
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=900, check=False
        )
    except FileNotFoundError:
        # Poetry not on PATH - fall back to bare pytest, else skip rather than wedge.
        try:
            proc = subprocess.run(
                ["pytest", *base_args],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            append_log("tests.log", f"SKIPPED (runner unavailable: {exc})")
            allow()
    except subprocess.TimeoutExpired:
        append_log("tests.log", "SKIPPED (timeout)")
        allow()

    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-25:])
    if proc.returncode != 0:
        append_log("tests.log", "FAIL")
        block(
            "Stop blocked by aegis run-tests: the unit suite is failing.\n"
            f"{tail}\n"
            "Fix the failing tests before ending the session, or export "
            "AEGIS_SKIP_TESTS=1 if this is intentional WIP."
        )
    append_log("tests.log", "PASS")
    allow()


if __name__ == "__main__":
    main()
