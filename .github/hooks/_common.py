"""Shared helpers for Aegis SWR Copilot hooks."""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

# Repo root is two levels up from .github/hooks/.
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
    """Return tool arguments from either Copilot or Claude-compatible payloads."""
    value = event.get("tool_input", event.get("toolArgs", {}))
    return value if isinstance(value, dict) else {}


def tool_name(event: dict[str, Any]) -> str:
    """Return the current tool name when present."""
    value = event.get("tool_name", event.get("toolName", ""))
    return str(value) if value is not None else ""


def edited_path(event: dict[str, Any]) -> Optional[Path]:
    """Resolve the file path targeted by a file-mutating tool call."""
    fields = tool_input(event)
    raw = fields.get("file_path") or fields.get("path") or fields.get("notebook_path")
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p)


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_log(filename: str, line: str) -> None:
    """Append a single timestamped line to a file under .claude/logs/."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / filename).open("a", encoding="utf-8") as fh:
        fh.write(f"{now_iso()} {line}\n")


def emit_json(payload: dict[str, Any]) -> None:
    """Write a single compact JSON payload to stdout."""
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))


def deny(message: str) -> None:
    """Deny a pre-tool action using Copilot's JSON decision format."""
    emit_json(
        {
            "permissionDecision": "deny",
            "permissionDecisionReason": message.rstrip(),
        }
    )
    sys.exit(0)


def block_turn(reason: str) -> None:
    """Force the agent to continue by blocking a Stop/agentStop hook."""
    emit_json({"decision": "block", "reason": reason.rstrip()})
    sys.exit(0)


def additional_context(message: str) -> None:
    """Inject additional context into the current Copilot turn."""
    emit_json({"additionalContext": message.rstrip()})
    sys.exit(0)


def allow() -> None:
    sys.exit(0)
