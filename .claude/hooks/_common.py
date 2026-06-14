"""Shared helpers for Aegis SWR Claude Code hooks.

All hooks are written in Python (not bash) because the canonical host is
Windows 10/11 and Python 3.12 is a hard project dependency - this guarantees the
hooks run identically on Windows, Linux, and macOS without a POSIX shell.

Hook protocol (Claude Code):
  * Hook input arrives as a single JSON object on stdin.
  * Exit code 0  -> allow / success.
  * Exit code 2  -> block the tool call (stderr is shown to Claude).
  * Any other exit code -> non-blocking error (stderr surfaced to the user).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Repo root is two levels up from .claude/hooks/.
REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / ".claude" / "logs"


def read_event() -> dict[str, Any]:
    """Parse the hook event JSON from stdin, tolerating an empty stream."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def tool_input(event: dict[str, Any]) -> dict[str, Any]:
    """Return the tool_input mapping from a PreToolUse/PostToolUse event."""
    value = event.get("tool_input", {})
    return value if isinstance(value, dict) else {}


def edited_path(event: dict[str, Any]) -> Optional[Path]:
    """Resolve the file path targeted by a Write/Edit/MultiEdit tool call."""
    fields = tool_input(event)
    raw = fields.get("file_path") or fields.get("path") or fields.get("notebook_path")
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_log(filename: str, line: str) -> None:
    """Append a single timestamped line to a file under .claude/logs/."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / filename).open("a", encoding="utf-8") as fh:
        fh.write(f"{now_iso()} {line}\n")


def block(message: str) -> "None":
    """Emit a blocking decision: stderr + exit 2."""
    sys.stderr.write(message.rstrip() + "\n")
    sys.exit(2)


def allow() -> "None":
    sys.exit(0)
