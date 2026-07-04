#!/usr/bin/env python3
"""PostToolUse / PostToolUseFailure audit for GitHub CLI usage."""
from __future__ import annotations

import re

from _common import allow, append_log, read_event, tool_input

TOKEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "<redacted-github-token>"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b"), "<redacted-openai-token>"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), "<redacted-anthropic-token>"),
    (re.compile(r"(?i)(authorization:\s*)(?:token|bearer)\s+\S+"), r"\1<redacted-auth>"),
)


def _is_github_cli(command: str) -> bool:
    return bool(re.search(r"(^|[;&|()]\s*)gh\s+", command))


def _sanitize(command: str) -> str:
    result = command
    for pattern, replacement in TOKEN_PATTERNS:
        result = pattern.sub(replacement, result)
    return " ".join(result.split())


def main() -> None:
    event = read_event()
    fields = tool_input(event)
    command = str(fields.get("command", ""))
    if not _is_github_cli(command):
        allow()

    status = "failed" if "error" in event else "completed"
    summary = _sanitize(command)[:240]
    append_log("github-actions.log", f"gh-cli {status} :: {summary}")
    allow()


if __name__ == "__main__":
    main()
