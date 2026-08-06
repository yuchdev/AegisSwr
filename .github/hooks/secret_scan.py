#!/usr/bin/env python3
"""Secret scanner - dual mode.

1. As a PreToolUse(Write|Edit|MultiEdit) hook: scans the *content about to be
   written*. If a likely secret is detected it denies the write.
2. As a CLI (``python secret_scan.py <file> [<file> ...]``): scans existing
   files on disk; used by the /secret-scan skill and the dep-audit flow.

Detection is pattern based and deliberately conservative-but-loud: it favours
catching real credentials over silence. Findings are logged to
.claude/logs/secret-scan.log. The Aegis codebase already redacts secrets at
runtime via ``SensitiveFilter`` - this hook stops them entering the repo at all.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

from _common import REPO_ROOT, allow, append_log, deny, edited_path, read_event, tool_input

# name -> compiled pattern. Patterns target high-signal credential shapes.
PATTERNS: dict[str, re.Pattern[str]] = {
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "AWS secret access key": re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}"),
    "Anthropic API key": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    "OpenAI API key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    "Generic assigned secret": re.compile(
        r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*['\"][^'\"\s]{8,}['\"]"
    ),
    "Postgres URL with password": re.compile(r"postg(?:res|resql)://[^:\s]+:[^@\s]+@"),
}

# Substrings that mark an obvious placeholder, so we do not cry wolf.
ALLOWLIST = (
    "example",
    "placeholder",
    "your-",
    "your_",
    "changeme",
    "dummy",
    "xxxx",
    "${",
    "<your",
    "redacted",
    "fake",
    "test",
)

SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".dmp", ".db"}


def _is_placeholder(line: str) -> bool:
    low = line.lower()
    return any(token in low for token in ALLOWLIST)


def scan_text(text: str) -> list[tuple[str, int, str]]:
    """Return (finding_name, line_number, line_excerpt) tuples."""
    hits: list[tuple[str, int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _is_placeholder(line):
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                hits.append((name, lineno, line.strip()[:120]))
    return hits


def _content_from_event(event: dict[str, object]) -> str:
    fields = tool_input(event)
    parts: list[str] = []
    for key in ("content", "new_string", "new_str"):
        val = fields.get(key)
        if isinstance(val, str):
            parts.append(val)
    edits = fields.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
                parts.append(edit["new_string"])
    return "\n".join(parts)


def _hook_mode():
    event = read_event()
    target = edited_path(event)
    if target and target.suffix.lower() in SKIP_SUFFIXES:
        allow()
    text = _content_from_event(event)
    if not text:
        allow()
    hits = scan_text(text)
    if hits:
        where = target.name if target else "<pending write>"
        for name, lineno, excerpt in hits:
            append_log("secret-scan.log", f"BLOCKED {where}:{lineno} [{name}] {excerpt}")
        report = "\n".join(f"  - line {ln}: {name}" for name, ln, _ in hits)
        deny(
            f"Blocked by aegis secret-scan: possible secret in {where}:\n{report}\n"
            "Never commit credentials. Use environment variables / ${VAR} references "
            "(see .mcp.json) or a secrets manager instead."
        )
    allow()


def _cli_mode(paths: Iterable[str]):
    total = 0
    for raw in paths:
        p = Path(raw)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if not p.is_file() or p.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, lineno, excerpt in scan_text(text):
            total += 1
            rel = p.relative_to(REPO_ROOT) if str(p).startswith(str(REPO_ROOT)) else p
            print(f"{rel}:{lineno}: {name}: {excerpt}")
    if total:
        print(f"\nsecret-scan: {total} potential secret(s) found.")
        sys.exit(1)
    print("secret-scan: clean.")
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli_mode(sys.argv[1:])
    else:
        _hook_mode()
