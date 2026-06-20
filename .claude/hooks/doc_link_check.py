#!/usr/bin/env python3
"""PostToolUse (Write|Edit|MultiEdit) + Stop: documentation reference integrity.

Runs ``scripts/check_doc_links.py`` so a docs edit never silently leaves a
dangling relative link or missing heading anchor.

* **PostToolUse** - when the edited file is Markdown, check that file's outbound
  links/anchors immediately (scoped, cheap).
* **Stop** - if any Markdown changed in the working tree this session, run the
  full repo doc-link scan, which also catches *inbound* breakage (e.g. a renamed
  heading that other docs still link to).

Always **non-blocking** (exit 0): it surfaces problems to the agent/user as a
reminder but never wedges a session. Flip ``_report`` to ``block`` (exit 2) to
make it a hard gate.
"""

from __future__ import annotations

import subprocess
import sys

from _common import REPO_ROOT, allow, append_log, edited_path, read_event

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


def main() -> None:
    event = read_event()
    target = edited_path(event)

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
    allow()


if __name__ == "__main__":
    main()
