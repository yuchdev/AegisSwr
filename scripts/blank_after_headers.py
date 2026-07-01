"""Ensure every Markdown ATX header is followed by exactly one blank line.

Scans ``*.md`` files and, for any ATX header (``#`` .. ``######`` followed by a
space or end-of-line) that is immediately followed by a non-blank line, inserts a
single blank line after the header. Headers already followed by a blank line (or
sitting at end-of-file) are left untouched, so the transform is idempotent.

Lines inside fenced code blocks (```` ``` ```` / ``~~~``) are never treated as
headers - a ``# comment`` in a shell snippet is not a heading.

Usage::

    python scripts/blank_after_headers.py            # rewrite all *.md in the repo
    python scripts/blank_after_headers.py --check     # report only; exit 1 if any need fixing
    python scripts/blank_after_headers.py docs/ a.md   # restrict to given paths
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

# Directories that hold vendored / generated Markdown we must not rewrite.
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".htmlcov",
    "__pycache__",
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
}

# ATX header: up to 3 leading spaces, 1-6 '#', then a space or end-of-line.
_HEADER_RE = re.compile(r"^ {0,3}#{1,6}(?: |$)")
# Opening/closing code fence: up to 3 leading spaces, then ``` or ~~~.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _is_blank(line: str) -> bool:
    return line.strip() == ""


def fix_lines(lines: list[str]) -> Optional[list[str]]:
    """Return rewritten lines, or ``None`` if no change was needed.

    :param lines: source lines *without* trailing newlines.
    :return: new list of lines when an insertion happened, else ``None``.
    """
    out: list[str] = []
    in_fence = False
    fence_marker: Optional[str] = None
    changed = False

    for i, line in enumerate(lines):
        out.append(line)

        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)[0]  # ` or ~
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue

        if in_fence:
            continue

        if _HEADER_RE.match(line):
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            # Insert a blank line only when a non-blank line follows the header.
            if nxt is not None and not _is_blank(nxt):
                out.append("")
                changed = True

    return out if changed else None


def iter_markdown(paths: list[Path]) -> list[Path]:
    """Expand the given paths into a sorted list of ``*.md`` files."""
    found: set[Path] = set()
    for p in paths:
        if p.is_file() and p.suffix == ".md":
            found.add(p)
        elif p.is_dir():
            for md in p.rglob("*.md"):
                if any(part in EXCLUDED_DIRS for part in md.parts):
                    continue
                found.add(md)
    return sorted(found)


def process(path: Path, check: bool) -> bool:
    """Process one file. Return ``True`` if it changed (or would change)."""
    original = path.read_text(encoding="utf-8")
    had_trailing_newline = original.endswith("\n")
    lines = original.splitlines()

    fixed = fix_lines(lines)
    if fixed is None:
        return False

    if not check:
        text = "\n".join(fixed) + ("\n" if had_trailing_newline else "")
        path.write_text(text, encoding="utf-8")
    return True


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to scan (default: current directory).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report files needing a fix and exit 1; do not modify anything.",
    )
    args = parser.parse_args(argv)

    targets = iter_markdown([Path(p) for p in args.paths])
    changed = [md for md in targets if process(md, args.check)]

    verb = "would fix" if args.check else "fixed"
    for md in changed:
        print(f"{verb}: {md}")
    print(f"\n{len(targets)} file(s) scanned, {len(changed)} {verb}.")

    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
