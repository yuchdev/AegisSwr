"""Git code backend.

Reads commit history, diffs, and blame from a real Git working tree by shelling
out to the ``git`` binary. All subprocess calls use list-form argv (never
``shell=True``), run with ``cwd=repo_path`` and a configurable timeout, and map
failures to :class:`CodeBackendError`.

See ``docs/specs/PRODUCTION_DESIGN_SPEC.md`` §6.5.1.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from aegis_swr.backends.base import CodeBackend
from aegis_swr.backends.code._paths import safe_repo_path
from aegis_swr.core.exceptions import CodeBackendError
from aegis_swr.core.schemas import BlameRecord, CommitRecord
from aegis_swr.config.settings import CodeBackendSettings

# Record/field separators chosen to never appear in commit metadata.
_RS = "\x1e"  # record separator (leads every commit)
_FS = "\x1f"  # field separator
_LOG_FORMAT = f"{_RS}%H{_FS}%an <%ae>{_FS}%aI{_FS}%s"


class GitCodeAdapter(CodeBackend):
    """Full Git history backend (``git log`` / ``git show`` / ``git blame``)"""

    def __init__(self, settings: CodeBackendSettings):
        self._settings = settings
        self._timeout = settings.git_timeout_seconds

    def get_commits_before(
        self,
        repo_path: str,
        before: datetime,
        window_hours: int = 2,
        limit: int = 10,
    ) -> list[CommitRecord]:
        self._assert_repo(repo_path)
        since = before - timedelta(hours=window_hours)
        out = self._git(
            repo_path,
            "log",
            f"--since={since.isoformat()}",
            f"--until={before.isoformat()}",
            f"--max-count={limit}",
            "--date=iso-strict",
            "--name-only",
            f"--pretty=format:{_LOG_FORMAT}",
        )
        return _parse_git_log(out)

    def get_file_diff(self, repo_path: str, file_path: str, commit_sha: str) -> str:
        self._assert_repo(repo_path)
        # Validate the path stays inside the repo (raises ValueError on traversal).
        safe_repo_path(repo_path, file_path)
        try:
            return self._git(repo_path, "show", commit_sha, "--", file_path)
        except CodeBackendError:
            # Unknown sha / path: no diff rather than a hard failure.
            return ""

    def blame(
        self,
        repo_path: str,
        file_path: str,
        line_range: tuple[int, int],
    ) -> list[BlameRecord]:
        self._assert_repo(repo_path)
        safe_repo_path(repo_path, file_path)
        start, end = line_range
        try:
            out = self._git(
                repo_path,
                "blame",
                "-L",
                f"{start},{end}",
                "--line-porcelain",
                "--",
                file_path,
            )
        except CodeBackendError:
            return []
        return _parse_blame_porcelain(out, start)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _assert_repo(self, repo_path: str):
        if not (Path(repo_path).expanduser() / ".git").exists():
            raise CodeBackendError(
                f"Not a git repository (no .git directory): {repo_path!r}. "
                "Use code provider 'filesystem' for non-VCS source trees."
            )

    def _git(self, repo_path: str, *args: str) -> str:
        try:
            proc = subprocess.run(  # noqa: S603 - list-form argv, no shell
                ["git", *args],
                cwd=str(Path(repo_path).expanduser()),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise CodeBackendError(
                "git binary not found on PATH; install Git or use code provider "
                "'filesystem'."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise CodeBackendError(
                f"git command timed out after {self._timeout}s: git {' '.join(args)}"
            ) from exc
        if proc.returncode != 0:
            raise CodeBackendError(
                f"git {' '.join(args)} failed (exit {proc.returncode}): "
                f"{proc.stderr.strip()}"
            )
        return proc.stdout


# ---------------------------------------------------------------------------
# Module-level parsers (unit-testable in isolation)
# ---------------------------------------------------------------------------


def _parse_git_log(text: str) -> list[CommitRecord]:
    """Parse ``git log --name-only`` output (record-separated by ``\\x1e``)"""
    commits: list[CommitRecord] = []
    for chunk in text.split(_RS):
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        header = lines[0]
        fields = header.split(_FS)
        if len(fields) < 4:
            logger.debug(f"Skipping malformed git log record: {header!r}")
            continue
        sha, author, iso_ts, subject = fields[0], fields[1], fields[2], fields[3]
        files = [ln.strip() for ln in lines[1:] if ln.strip()]
        commits.append(
            CommitRecord(
                sha=sha,
                message=subject,
                author=author,
                timestamp=_parse_iso(iso_ts),
                files_changed=files,
            )
        )
    return commits


def _parse_blame_porcelain(text: str, first_line: int) -> list[BlameRecord]:
    """Parse ``git blame --line-porcelain`` output into BlameRecords"""
    records: list[BlameRecord] = []
    line_number = first_line
    sha = ""
    author = "unknown"
    ts: datetime | None = None
    for raw in text.splitlines():
        if raw.startswith("\t"):
            # The content line terminates a porcelain block.
            records.append(
                BlameRecord(
                    line_number=line_number,
                    sha=sha,
                    author=author,
                    timestamp=ts or _epoch(),
                    content=raw[1:],
                )
            )
            line_number += 1
            sha, author, ts = "", "unknown", None
            continue
        parts = raw.split(" ", 1)
        head = parts[0]
        if len(head) == 40 and all(c in "0123456789abcdef" for c in head):
            sha = head
        elif raw.startswith("author "):
            author = raw[len("author ") :].strip()
        elif raw.startswith("author-time "):
            try:
                ts = datetime.fromtimestamp(int(raw[len("author-time ") :].strip()))
            except ValueError:
                ts = None
    return records


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return _epoch()


def _epoch() -> datetime:
    return datetime.fromtimestamp(0)
