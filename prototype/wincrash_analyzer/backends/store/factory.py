"""Factory for storage backend instantiation"""
from wincrash_analyzer.backends.store.base import StorageBackendBase
from wincrash_analyzer.config import get_option


def create_storage_backend(backend: str, config: str | None = None) -> StorageBackendBase:
    """
    Instantiate and return the requested storage backend.

    @param backend: The identifier of the storage backend.
    @param config: Configuration string (e.g., directory path or database path).
    @return: An instance of the requested storage backend.
    @raises ValueError: If an unknown backend identifier is provided.
    """
    store_opt = get_option("store")
    if backend not in store_opt.choices:
        raise ValueError(f"Unknown storage backend: {backend!r}. Valid choices are: {store_opt.choices}")

    if backend == "filesystem":
        from wincrash_analyzer.backends.store.filesystem import FilesystemBackend
        return FilesystemBackend(output_dir=config) if config else FilesystemBackend()
    if backend == "sqlite":
        from wincrash_analyzer.backends.store.sqlite import SQLiteBackend
        return SQLiteBackend(db_path=config) if config else SQLiteBackend()
    
    raise ValueError(f"Storage backend {backend!r} is in schema but not implemented in factory.")
