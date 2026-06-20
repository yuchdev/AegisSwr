"""Code backend factory.

The ``CodeBackend`` is always optional: when ``enabled`` is false the factory
returns ``None`` and Data Adapter Stage 8 is skipped.
"""
from __future__ import annotations

from typing import Optional
from aegis_swr.backends.code.filesystem_adapter import FilesystemCodeAdapter
from aegis_swr.backends.code.git_adapter import GitCodeAdapter
from aegis_swr.backends.base import CodeBackend
from aegis_swr.config.settings import CodeBackendSettings

__all__ = [
    "FilesystemCodeAdapter",
    "GitCodeAdapter",
    "create_code_backend",
]


def create_code_backend(settings: CodeBackendSettings) -> Optional[CodeBackend]:
    """Return the configured ``CodeBackend`` or ``None`` when disabled"""
    if not settings.enabled:
        return None
    if settings.provider == "git":
        return GitCodeAdapter(settings)
    if settings.provider == "filesystem":
        return FilesystemCodeAdapter(settings)
    raise ValueError(
        f"Unknown code provider: {settings.provider!r}. Valid choices: git, filesystem."
    )
