"""Filesystem code backend (no VCS).

Treats a plain source directory as the "repository" so the :class:`CodeBackend`
contract holds without Git. Used for vendored / exported source trees, archived
snapshots, or air-gapped drops with no ``.git``. History is synthesized from file
modification times; blame carries no real authorship.

See ``docs/specs/generic_implementation_plan.md`` C.5 CodeBackend.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loguru import logger

from aegis_swr.backends.base import CodeBackend
from aegis_swr.backends.code.paths import safe_repo_path
from aegis_swr.config.settings import CodeBackendSettings
from aegis_swr.core.schemas import BlameRecord, CommitRecord

# Directories never worth walking for crash attribution.
_PRUNE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


class FilesystemCodeAdapter(CodeBackend):
    """No-VCS fallback: directory walk + synthesized mtime "commits"""

    def __init__(self, settings: CodeBackendSettings):
        """Store the code-backend *settings* for the VCS-less directory walk."""
        self._settings = settings

    def get_commits_before(
        self,
        repo_path: str,
        before: datetime,
        window_hours: int = 2,
        limit: int = 10,
    ) -> list[CommitRecord]:
        """Synthesize pseudo-commits from file mtimes within the given window.

        :param repo_path: the source directory to walk.
        :param before: upper bound (inclusive) of the mtime window.
        :param window_hours: how many hours before *before* to include.
        :param limit: maximum number of records to return (0 means all).
        :return: mtime-derived :class:`CommitRecord` list, newest first.
        """
        root = Path(repo_path).expanduser()
        if not root.is_dir():
            logger.warning(f"FilesystemCodeAdapter: not a directory: {repo_path!r}")
            return []
        since = before - timedelta(hours=window_hours)
        # Match mtime awareness to *before* so the window comparison never mixes
        # naive and aware datetimes.
        tz = before.tzinfo
        records: list[CommitRecord] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS and not d.startswith(".")]
            for name in filenames:
                fpath = Path(dirpath) / name
                try:
                    st_mtime = fpath.stat().st_mtime
                except OSError as exc:
                    logger.debug("FilesystemAdapter: skipping {}: {}", fpath, exc)
                    continue
                mtime = datetime.fromtimestamp(st_mtime, tz=tz) if tz is not None else datetime.fromtimestamp(st_mtime)
                if not (since <= mtime <= before):
                    continue
                rel = fpath.relative_to(root).as_posix()
                records.append(
                    CommitRecord(
                        sha="fs:" + hashlib.sha1(rel.encode()).hexdigest()[:12],  # noqa: S324
                        message="filesystem mtime",
                        author="unknown",
                        timestamp=mtime,
                        files_changed=[rel],
                    )
                )
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records if limit == 0 else records[:limit]

    def get_file_diff(self, repo_path: str, file_path: str, commit_sha: str) -> str:
        """Return the current file contents (no VCS history), or ``""`` if unreadable."""
        path = safe_repo_path(repo_path, file_path)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, IsADirectoryError) as exc:
            logger.debug("FilesystemAdapter.get_file_diff: file not readable at {}: {}", path, exc)
            return ""
        return f"--- (no VCS history)\n{content}"

    def blame(
        self,
        repo_path: str,
        file_path: str,
        line_range: tuple[int, int],
    ) -> list[BlameRecord]:
        """Return synthesized blame records (no author history) for *line_range*."""
        path = safe_repo_path(repo_path, file_path)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except (FileNotFoundError, IsADirectoryError) as exc:
            logger.debug("FilesystemAdapter.blame: file not readable at {}: {}", path, exc)
            return []
        start, end = line_range
        sha = "fs:" + hashlib.sha1(file_path.encode()).hexdigest()[:12]  # noqa: S324
        records: list[BlameRecord] = []
        for line_number in range(start, min(end, len(lines)) + 1):
            records.append(
                BlameRecord(
                    line_number=line_number,
                    sha=sha,
                    author="unknown",
                    timestamp=mtime,
                    content=lines[line_number - 1],
                )
            )
        return records
