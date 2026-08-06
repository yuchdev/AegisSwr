#!/usr/bin/env python3
"""Stop hook - gate the end of a turn on a green unit suite."""

from __future__ import annotations

import os
import subprocess

from _common import REPO_ROOT, allow, append_log, block_turn, read_event


def main():
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
    cmd = ["uv", "run", "pytest", *base_args]
    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=900, check=False)
    except FileNotFoundError:
        # uv not on PATH - fall back to bare pytest, else skip rather than wedge.
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
        block_turn(
            "Stop blocked by aegis run-tests: the unit suite is failing.\n"
            f"{tail}\n"
            "Fix the failing tests before ending the session, or export "
            "AEGIS_SKIP_TESTS=1 if this is intentional WIP."
        )
    append_log("tests.log", "PASS")
    allow()


if __name__ == "__main__":
    main()
