#!/usr/bin/env python3
"""PostToolUse / Stop: documentation reference integrity."""

from __future__ import annotations

import os
import subprocess
import sys

from _common import REPO_ROOT, additional_context, allow, append_log, edited_path, read_event

CHECKER = REPO_ROOT / "scripts" / "check_doc_links.py"


def _run_checker(paths: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            [sys.executable, str(CHECKER), "--check", *paths],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"doc_link_check: checker unavailable ({exc}); skipped.\n")
        return 0, ""
    return proc.returncode, (proc.stdout + proc.stderr)


def _changed_markdown() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln.strip().lower().endswith(".md")]


def main():
    event = read_event()
    target = edited_path(event)
    stop_mode = event.get("hook_event_name") == "Stop" or not target

    if target is not None:
        # PostToolUse: only act on Markdown; scope to the edited file.
        if target.suffix.lower() != ".md" or not target.exists():
            allow()
        scan_paths = [str(target)]
    else:
        # Stop: only when docs changed this session; then full scan (catches inbound).
        if not _changed_markdown():
            allow()
        scan_paths = []

    code, output = _run_checker(scan_paths)
    if code != 0 and output.strip():
        append_log("doc-link-check.log", "dangling documentation references found")
        sys.stderr.write(
            "doc_link_check: dangling documentation references (non-blocking) -\n"
            + output.rstrip()
            + "\nRun `/link-check` (or `python scripts/check_doc_links.py`) to review.\n"
        )
        if not stop_mode:
            tail = "\n".join(output.strip().splitlines()[-8:])
            additional_context(
                "Documentation link checker found issues after the edit.\n"
                f"{tail}\n"
                "Run `/link-check` (or `python scripts/check_doc_links.py`) before finishing."
            )
    if stop_mode and os.environ.get("AEGIS_DOC_LINK_WARNED") != "1":
        os.environ["AEGIS_DOC_LINK_WARNED"] = "1"
    allow()


if __name__ == "__main__":
    main()
