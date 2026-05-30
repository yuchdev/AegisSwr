"""Log backend factory.

The ``LogBackend`` is always optional: the Data Adapter only queries it in
Stage 4 when a service name and incident timestamp are both available.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aegis_swr.backends.log.file_adapter import FileLogAdapter
from aegis_swr.backends.log.fluent_adapter import FluentAdapter

if TYPE_CHECKING:
    from aegis_swr.backends.base import LogBackend
    from aegis_swr.config.settings import LogBackendSettings

__all__ = [
    "FileLogAdapter",
    "FluentAdapter",
    "create_log_backend",
]


def create_log_backend(settings: LogBackendSettings) -> LogBackend | None:
    """Return the configured ``LogBackend``.

    ``file`` and ``fluent`` are supported; ``elk`` is deferred and raises
    ``NotImplementedError``.
    """
    if settings.provider == "file":
        return FileLogAdapter(settings)
    if settings.provider == "fluent":
        return FluentAdapter(settings)
    if settings.provider == "elk":
        raise NotImplementedError("ELKAdapter is deferred; use 'file' or 'fluent'.")
    raise ValueError(
        f"Unknown log provider: {settings.provider!r}. Valid choices: file, fluent."
    )
