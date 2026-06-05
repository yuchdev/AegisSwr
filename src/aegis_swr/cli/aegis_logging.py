"""CLI logging configuration: loguru level + sensitive-data redaction"""
from __future__ import annotations

import logging
import re
import sys

from loguru import logger

# Matches common API key patterns in log output.
_REDACT_RE = re.compile(
    r"(ANTHROPIC_API_KEY|OPENAI_API_KEY|api[_-]?key)\s*[=:]\s*\S+"
    r"|sk-ant-[A-Za-z0-9_-]+"
    r"|sk-[A-Za-z0-9_-]{10,}",
    re.IGNORECASE,
)

# Third-party loggers that emit verbose HTTP request/response bodies and
# other debug-level details; always clamped to WARNING to prevent sensitive
# data leakage at user-requested INFO level.
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


def configure_logging(severity: str = "INFO"):
    """Remove the default loguru handler and add a stderr sink at *severity*

    Also clamps all third-party loggers in _NOISY_LIBRARY_LOGGERS to WARNING
    level to prevent HTTP bodies containing sensitive data from being logged.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=severity.upper(),
        format="<green>{time:HH:mm:ss}</green> <level>{level: <8}</level> {message}",
        filter=_sensitive_filter,
    )
    # Clamp noisy third-party loggers to WARNING regardless of root level.
    for logger_name in NOISY_LIBRARY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
