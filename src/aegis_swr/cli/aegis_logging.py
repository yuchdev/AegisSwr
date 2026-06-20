"""CLI logging configuration: loguru level + sensitive-data redaction"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

#: Classic file-log line format (no ANSI colour - written to a plain text file).
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"

#: Basename of the rotating application log written under ``--log-dir``.
LOG_FILENAME = "aegis-swr.log"

# Matches common API key patterns in log output.
_REDACT_RE = re.compile(
    r"(ANTHROPIC_API_KEY|OPENAI_API_KEY|AWS_BEARER_TOKEN_BEDROCK|api[_-]?key|"
    r"bearer)\s*[=:]\s*\S+"
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


#: Coloured stderr line format (always-on console sink).
_STDERR_FORMAT = "<green>{time:HH:mm:ss}</green> <level>{level: <8}</level> {message}"

#: Application log sinks. ``file`` is fully implemented; ``elk``/``fluent`` are
#: stubs (the log-subsystem split, plan Part III - D3): they warn and fall back to
#: the file/stderr sinks, leaving a registration seam for the real emitters.
SUPPORTED_SINKS = ("file", "elk", "fluent")


def _add_file_sink(log_dir: str, level: str) -> bool:
    """Add the rotating ``<log_dir>/aegis-swr.log`` sink at *level*.

    Plain text, timestamped, rotated at 10 MB, last 10 files retained, with the
    API-key redaction filter applied. Returns ``True`` when added; ``False`` (with
    a warning) if the directory cannot be created - stderr logging is never lost.

    ``delay=True`` defers creating the file until the first record is written, so
    the early bootstrap sink (see ``commands.analyze``) leaves no empty log file
    behind when the run logs nothing before logging is re-applied.
    """
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
            delay=True,
        )
    except OSError as exc:
        logger.warning(f"Could not open log directory {log_dir!r}: {exc}")
        return False
    return True


def _register_elk_sink(level: str, *, elk_url: Optional[str]) -> bool:
    """Extension seam for the ELK application-log sink.

    Not yet implemented (plan Part III - Phase E): returns ``False`` so the caller
    falls back to the file/stderr sinks. A future implementation will POST batched,
    redacted records to *elk_url* and return ``True``.
    """
    return False


def _register_fluent_sink(
    level: str, *, fluent_host: Optional[str], fluent_port: Optional[int]
) -> bool:
    """Extension seam for the Fluentd / Fluent Bit application-log sink.

    Not yet implemented (plan Part III - Phase E): returns ``False`` so the caller
    falls back to the file/stderr sinks. A future implementation will forward
    redacted records to ``fluent_host:fluent_port`` and return ``True``.
    """
    return False


def configure_logging(
    severity: str = "INFO",
    *,
    log_dir: Optional[str] = None,
    sink: str = "file",
    elk_url: Optional[str] = None,
    fluent_host: Optional[str] = None,
    fluent_port: Optional[int] = None,
):
    """Configure loguru: a stderr sink at *severity* plus the selected *sink*.

    *severity* is any loguru level name - ``TRACE``, ``DEBUG``, ``INFO``,
    ``WARNING``, or ``ERROR`` (``TRACE`` is the most verbose). Regardless of the
    chosen level, every third-party logger in ``NOISY_LIBRARY_LOGGERS`` is clamped
    to WARNING to prevent HTTP bodies containing sensitive data from being logged.

    *sink* selects where Aegis's *own* diagnostic log is persisted (this is
    unrelated to ``backends.log``, which ingests the investigated system's logs):

    * ``file``  - a classic rotating ``<log_dir>/aegis-swr.log`` written at
      *severity*, added only when *log_dir* is given.
    * ``elk`` / ``fluent`` - **not yet implemented** (plan Part III, Phase E): they
      log a warning and fall back to the file/stderr sinks so logging is never
      lost. The connection settings (*elk_url* / *fluent_host* / *fluent_port*) are
      accepted now and consumed once the emitters land (see ``_register_*_sink``).

    The stderr sink and the API-key redaction filter apply to every sink.
    """
    level = severity.upper()
    logger.remove()
    logger.add(sys.stderr, level=level, format=_STDERR_FORMAT, filter=_sensitive_filter)

    normalized = (sink or "file").lower()
    handled = False
    if normalized == "elk":
        handled = _register_elk_sink(level, elk_url=elk_url)
    elif normalized == "fluent":
        handled = _register_fluent_sink(level, fluent_host=fluent_host, fluent_port=fluent_port)

    # The file sink is the default and the fallback for an unimplemented or
    # unknown sink. Add it before the warning so the notice is captured by it too.
    if log_dir and not handled:
        _add_file_sink(log_dir, level)

    if normalized not in SUPPORTED_SINKS:
        logger.warning(f"Unknown application log sink {normalized!r}; using the file sink.")
    elif normalized in ("elk", "fluent") and not handled:
        logger.warning(
            f"Application log sink {normalized!r} is not yet implemented; falling "
            "back to the file sink (plan Part III - Phase E)."
        )

    # Clamp noisy third-party loggers to WARNING regardless of root level.
    for logger_name in NOISY_LIBRARY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
