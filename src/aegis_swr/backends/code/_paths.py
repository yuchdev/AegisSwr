"""Shared path-safety helper for code backends.

Both ``GitCodeAdapter`` and ``FilesystemCodeAdapter`` treat ``file_path`` as
repo-relative. This resolves it against the repository root and refuses any path
that escapes that root, blocking ``../`` traversal in the same spirit as
``FilesystemStore._safe_path``.
"""
from __future__ import annotations

from pathlib import Path


def safe_repo_path(repo_path: str, file_path: str) -> Path:
    """Resolve *file_path* (repo-relative) inside *repo_path*.

    Raises ``ValueError`` if the resolved path escapes the repository root.
    """
    base = Path(repo_path).expanduser().resolve()
    candidate = (base / file_path).resolve()
    if not str(candidate).startswith(str(base)):
        raise ValueError(f"Path traversal attempt: {file_path!r} escapes {base}")
    return candidate
