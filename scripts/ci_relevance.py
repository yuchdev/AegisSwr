"""Decide whether a push/PR's file changes justify running the full CI pipeline.

Used as a gate job at the top of .github/workflows/ci.yml and coverage.yml: every
other job depends on this one and only runs when its ``run_ci`` output is
``"true"``. The policy is deny-by-default for safety: a changeset skips CI only
when *every* changed file matches a known documentation/agent/skill pattern that
cannot affect build, lint, or test outcomes. Any file type this script has not
been taught about — including one added to the repo after this script was
written — is treated as a reason to run, not a reason to skip.

Local usage (no GitHub Actions environment required):
    python scripts/ci_relevance.py --files a.py docs/readme.md

Inside a workflow, the file list is derived from git via environment variables
the calling step must set explicitly (see .github/workflows/_ci-relevance-gate.yml
for the exact wiring) — GitHub Actions does not export the pull_request base SHA
or the push before/after SHAs as plain environment variables on its own, only as
``${{ github.event.* }}`` template expressions, so the workflow step has to pass
them through.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

#: A changed file matching one of these is sufficient, on its own, to run the
#: full pipeline. This list exists for fast, self-documenting intent - the real
#: safety net is that anything NOT matched by NEVER_RUN_PATTERNS also runs (see
#: `decide`), so this list does not need to be exhaustive.
ALWAYS_RUN_PATTERNS: tuple[str, ...] = (
    "*.py",
    "*.pyi",
    "*.toml",
    "uv.lock",
    "requirements*.txt",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/hooks/*.py",
    "*.cfg",
    "*.ini",
    "Dockerfile",
    "Dockerfile.*",
)

#: A changed file matching one of these never, by itself, justifies running the
#: full pipeline. NOTE: fnmatch's "*" already matches "/" (it is not
#: path-segment-aware), so "docs/*.md" already covers nested paths like
#: "docs/adr/0005-foo.md" without needing a separate "**" form.
NEVER_RUN_PATTERNS: tuple[str, ...] = (
    "docs/*.md",
    ".claude/agents/*",
    ".claude/skills/*",
    ".claude/CLAUDE.md",
    ".github/copilot/agents/*",
    ".github/copilot/skills/*",
    ".github/copilot-instructions.md",
    ".junie/agents/*",
    ".junie/skills/*",
    "LICENSE",
    "LICENSE.*",
    ".gitignore",
)

#: Root-only patterns (no "/" in the path), checked separately from
#: NEVER_RUN_PATTERNS: a bare "*.md" under fnmatch would also match nested
#: paths such as "docs/foo.md" or "src/pkg/README.md", but the intent here is
#: specifically top-level files like README.md / CHANGELOG.md.
NEVER_RUN_ROOT_ONLY_PATTERNS: tuple[str, ...] = ("*.md",)

#: git's well-known empty-tree object hash; diffing against it lists every file
#: in the target commit, which is exactly what "before" should mean at the tip
#: of a brand-new branch (GitHub reports `before` as all zeros in that case).
_EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    """True if *path* matches at least one of *patterns* (fnmatch semantics)."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def is_forced_run(path: str) -> bool:
    """True if *path* alone is reason enough to run the full pipeline."""
    return _matches_any(path, ALWAYS_RUN_PATTERNS)


def is_skippable(path: str) -> bool:
    """True if *path* is known to never affect build/lint/test outcomes."""
    if _matches_any(path, NEVER_RUN_PATTERNS):
        return True
    return "/" not in path and _matches_any(path, NEVER_RUN_ROOT_ONLY_PATTERNS)


@dataclass(frozen=True)
class Decision:
    """The run/skip outcome for a changeset, plus a human-readable reason."""

    run_ci: bool
    reason: str


def decide(changed_files: Optional[list[str]]) -> Decision:
    """Classify a changeset; ``changed_files=None`` means "no diff available".

    :param changed_files: paths changed by this push/PR, or ``None`` when the
        triggering event has no meaningful diff to compute (schedule,
        workflow_dispatch, or a diff that could not be resolved) - callers
        must pass ``None`` rather than an empty list in that case, since an
        empty list is a real (if unusual) "nothing changed" result.
    :returns: the run/skip decision plus a short human-readable reason,
        surfaced in workflow logs so a skipped run is easy to audit.
    """
    if changed_files is None:
        return Decision(True, "no diff available for this trigger; running full pipeline")

    files = [f for f in changed_files if f.strip()]
    if not files:
        return Decision(True, "diff was empty/unreadable; running full pipeline (fail-safe)")

    forced = [f for f in files if is_forced_run(f)]
    if forced:
        return Decision(True, f"{len(forced)} file(s) matched an always-run pattern, e.g. {forced[0]}")

    unclassified = [f for f in files if not is_skippable(f)]
    if unclassified:
        return Decision(True, f"{len(unclassified)} file(s) not on the skip-list, e.g. {unclassified[0]}")

    return Decision(False, f"all {len(files)} changed file(s) matched skip-only patterns")


def _run_git(*args: str) -> str:
    """Run a git subcommand and return its captured stdout."""
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout


def get_changed_files_from_git() -> Optional[list[str]]:
    """Resolve the changed-file list for the current GitHub Actions event.

    :returns: changed file paths, or ``None`` when this event/trigger has no
        diffable before/after pair (schedule, workflow_dispatch) or the diff
        could not be computed (e.g. the base commit is unexpectedly missing) -
        in every such case the caller must fail safe and run the full
        pipeline, so ``None`` is a distinct outcome from an empty list.
    """
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")

    if event_name == "pull_request":
        base_sha = os.environ.get("PR_BASE_SHA", "")
        head_sha = os.environ.get("PR_HEAD_SHA") or "HEAD"
        if not base_sha:
            return None
        try:
            subprocess.run(
                ["git", "fetch", "--depth=1", "origin", base_sha],
                check=True,
                capture_output=True,
                text=True,
            )
            diff = _run_git("diff", "--name-only", f"{base_sha}...{head_sha}")
        except subprocess.CalledProcessError as exc:
            print(f"ci_relevance: could not diff against base {base_sha}: {exc}", file=sys.stderr)
            return None
        return diff.splitlines()

    if event_name == "push":
        before = os.environ.get("GITHUB_EVENT_BEFORE", "")
        after = os.environ.get("GITHUB_EVENT_AFTER") or os.environ.get("GITHUB_SHA") or "HEAD"
        if not before or set(before) == {"0"}:
            before = _EMPTY_TREE_SHA
        try:
            diff = _run_git("diff", "--name-only", before, after)
        except subprocess.CalledProcessError as exc:
            print(f"ci_relevance: could not diff {before}..{after}: {exc}", file=sys.stderr)
            return None
        return diff.splitlines()

    # schedule, workflow_dispatch, merge_group, etc.: nothing to diff against.
    return None


def _write_github_output(run_ci: bool):
    """Append the ``run_ci`` output to ``$GITHUB_OUTPUT``, or print it locally."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    value = "true" if run_ci else "false"
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"run_ci={value}\n")
    else:
        print(f"run_ci={value}")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point: decide run/skip and emit the ``run_ci`` output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Explicit changed-file list for local testing; bypasses git/GitHub Actions env entirely.",
    )
    args = parser.parse_args(argv)

    changed = args.files if args.files is not None else get_changed_files_from_git()
    decision = decide(changed)

    print(f"run_ci={'true' if decision.run_ci else 'false'} ({decision.reason})", file=sys.stderr)
    if changed:
        print("Changed files:", file=sys.stderr)
        for path in changed:
            print(f"  {path}", file=sys.stderr)

    _write_github_output(decision.run_ci)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
