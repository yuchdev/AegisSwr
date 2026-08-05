"""Local-file log backend.

Returns log lines from local ``.log`` / ``.txt`` files whose parsed timestamp
falls inside the requested window, optionally filtered by severity. The
``service`` name resolves to files under ``settings.file_root`` (when set).

See ``docs/specs/generic_implementation_plan.md`` C.4 LogBackend
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from aegis_swr.backends.base import LogBackend
from aegis_swr.config.settings import LogBackendSettings
from aegis_swr.core.data_adapter import _parse_timestamp, _severity_token
from aegis_swr.core.exceptions import LogBackendError


def _safe_under(base: Path, candidate: Path) -> bool:
    """Return True when *candidate* resolves to a path inside *base*."""
    return str(candidate.resolve()).startswith(str(base.resolve()))


class FileLogAdapter(LogBackend):
    """Reads windowed, severity-filtered log lines from local files"""

    def __init__(self, settings: LogBackendSettings):
        """Store the log-backend *settings* (file root) for later queries."""
        self._settings = settings

    async def query_window(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity_levels: Optional[list[str]] = None,
    ) -> list[str]:
        """Return windowed, severity-filtered log lines off the event loop thread.

        :param service: the service whose log files to read.
        :param start_time: inclusive window start.
        :param end_time: inclusive window end.
        :param severity_levels: optional severity allowlist (upper-cased).
        :return: the matching log lines in file order.
        """
        return await asyncio.to_thread(self._sync_query, service, start_time, end_time, severity_levels)

    def _sync_query(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity_levels: Optional[list[str]],
    ) -> list[str]:
        """Read and filter the resolved log files by time window and severity."""
        files = self._resolve_files(service)
        if not files:
            return []
        levels = {s.upper() for s in severity_levels} if severity_levels else None
        kept: list[str] = []
        for path in files:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except (FileNotFoundError, IsADirectoryError) as exc:
                logger.debug("FileLogAdapter: skipping unreadable path {}: {}", path, exc)
                continue
            except OSError as exc:
                raise LogBackendError(f"File log query failed for {service!r}: {exc}") from exc
            for line in content.splitlines():
                ts = _parse_timestamp(line, start_time)
                if ts is None or not (start_time <= ts <= end_time):
                    continue
                if levels is not None:
                    token = _severity_token(line)
                    if token is not None and token not in levels:
                        continue
                kept.append(line)
        return kept

    def _resolve_files(self, service: str) -> list[Path]:
        """Resolve the log files for *service* under the configured root, safely."""
        if self._settings.file_root is None:
            return []
        base = Path(self._settings.file_root).expanduser().resolve()
        if not base.is_dir():
            logger.warning(f"FileLogAdapter: file_root is not a directory: {base}")
            return []
        # Reject service names that try to escape the root via path separators.
        if "/" in service or "\\" in service or ".." in service:
            logger.warning(f"FileLogAdapter: rejecting unsafe service name {service!r}")
            return []
        matches: list[Path] = []
        for pattern in (f"{service}*.log", f"{service}*.txt"):
            try:
                candidates = list(base.glob(pattern))
            except (ValueError, NotImplementedError) as exc:
                logger.debug("FileLogAdapter._resolve_files: glob pattern {!r} failed: {}", pattern, exc)
                continue
            for candidate in candidates:
                if _safe_under(base, candidate) and candidate.is_file():
                    matches.append(candidate)
        if not matches:
            logger.debug(f"FileLogAdapter: no files for service {service!r} under {base}")
        return sorted(set(matches))
