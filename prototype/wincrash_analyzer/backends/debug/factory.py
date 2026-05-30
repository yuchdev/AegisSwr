"""Factory for debugger backend instantiation."""
from wincrash_analyzer.backends.debug.base import DebugBackendBase
from wincrash_analyzer.config import get_option


def create_debug_backend(engine: str, cdb_path: str = "cdb.exe") -> DebugBackendBase:
    """
    Instantiate and return the requested debugger backend.

    @param engine: The identifier of the debug engine.
    @param cdb_path: Path to the cdb.exe binary.
    @return: An instance of the requested debugger backend.
    @raises ValueError: If an unknown engine identifier is provided.
    """
    engine_opt = get_option("engine")
    if engine not in engine_opt.choices:
        raise ValueError(f"Unknown debug engine: {engine!r}. Valid choices are: {engine_opt.choices}")

    if engine == "cdb":
        from wincrash_analyzer.backends.debug.cdb import CDBBackend
        return CDBBackend(cdb_path=cdb_path)
    if engine == "js":
        from wincrash_analyzer.backends.debug.js_provider import JSProviderBackend
        return JSProviderBackend()
    
    raise ValueError(f"Debug engine {engine!r} is in schema but not implemented in factory.")
