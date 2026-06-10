"""CLI logging configuration: loguru level + sensitive-data redaction"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

#: Classic file-log line format (no ANSI colour - written to a plain text file).
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} - {message}"
)

#: Basename of the rotating application log written under ``--log-dir``.
LOG_FILENAME = "aegis-swr.log"

# Matches common API key patterns in log output.
_REDACT_RE = re.compile(
    r"(ANTHROPIC_API_KEY|OPENAI_API_KEY|api[_-]?key)\s*[=:]\s*\S+"
    r"|sk-ant-[A-Za-z0-9_-]+"
    r"|sk-[A-Za-z0-9_-]{10,}",
    re.IGNORECASE,
)

# Third-party loggers that emit verbose HTTP request/response bodies and
# other debug-level details; always clamped to WARNING to prevent sensitive
# data leakage at user-requested TRACE / DEBUG / INFO levels.
NOISY_LIBRARY_LOGGERS = (
    "anthropic",
    "openai",
    "httpx",
    "google.auth",
    "google.api_core",
)


def _sensitive_filter(record: object) -> bool:
    """Loguru filter that replaces API key values with ``[REDACTED]``"""
    if isinstance(record, dict):
        record["message"] = _REDACT_RE.sub("[REDACTED]", str(record["message"]))
    return True


def configure_logging(severity: str = "INFO", log_dir: Optional[str] = None):
    """Configure loguru: a stderr sink at *severity* plus an optional log file.

    *severity* is any loguru level name - ``TRACE``, ``DEBUG``, ``INFO``,
    ``WARNING``, or ``ERROR`` (``TRACE`` is the most verbose). Regardless of the
    chosen level, every third-party logger in ``NOISY_LIBRARY_LOGGERS`` is
    clamped to WARNING to prevent HTTP bodies containing sensitive data from
    being logged.

    When *log_dir* is given, a classic rotating log file
    (``<log_dir>/aegis-swr.log``) is added at the same severity: plain text,
    timestamped, rotated at 10 MB and retained for the last 10 files. The same
    API-key redaction filter is applied to the file sink. If the directory
    cannot be created the file sink is skipped with a warning - stderr logging
    is never lost.
    """
    level = severity.upper()
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> <level>{level: <8}</level> {message}",
        filter=_sensitive_filter,
    )

    if log_dir:
        try:
            directory = Path(log_dir).expanduser()
            directory.mkdir(parents=True, exist_ok=True)
            logger.add(
                directory / LOG_FILENAME,
                level=level,
                format=_FILE_FORMAT,
                filter=_sensitive_filter,
                rotation="10 MB",
                retention=10,
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"Could not open log directory {log_dir!r}: {exc}")

    # Clamp noisy third-party loggers to WARNING regardless of root level.
    for logger_name in NOISY_LIBRARY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
