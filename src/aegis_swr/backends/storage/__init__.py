"""Storage backend factory"""
from __future__ import annotations

from aegis_swr.backends.base import ObjectStore, RelationalStore
from aegis_swr.backends.storage.filesystem_store import FilesystemStore
from aegis_swr.backends.storage.postgres_store import PostgresStore
from aegis_swr.backends.storage.s3_store import S3Store
from aegis_swr.backends.storage.sqlite_store import SQLiteStore
from aegis_swr.config.settings import StorageSettings

__all__ = [
    "FilesystemStore",
    "PostgresStore",
    "S3Store",
    "SQLiteStore",
    "create_storage_backends",
]


def create_storage_backends(
    settings: StorageSettings,
) -> tuple[RelationalStore | None, ObjectStore | None]:
    """Return ``(relational, object_store)`` for the configured provider.

    ``FilesystemStore`` and ``S3Store`` implement both interfaces so they are
    returned as both components. ``SQLiteStore`` and ``PostgresStore`` provide
    only ``RelationalStore``; the object-store slot is ``None``.
    """
    if settings.provider == "filesystem":
        fs = FilesystemStore(settings)
        return fs, fs
    if settings.provider == "sqlite":
        return SQLiteStore(settings), None
    if settings.provider == "s3":
        s3 = S3Store(settings)
        return s3, s3
    if settings.provider == "postgres":
        return PostgresStore(settings), None
    raise ValueError(
        f"Unknown storage provider: {settings.provider!r}. "
        "Valid choices: filesystem, sqlite, s3, postgres."
    )
