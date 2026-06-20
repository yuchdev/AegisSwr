"""Custom exception hierarchy for WinCrash Analyzer"""


class WinCrashError(Exception):
    """
    Base for all application-specific errors.
    """

    def __init__(self, message, code=500):
        """
        Initialize the error.

        @param message: The error message.
        @param code: The error code (default 500).
        """
        super().__init__(message)
        self.code = code


# Backwards-compatible alias.
WinCrashAnalyzerError = WinCrashError


class DumpFileNotFoundError(WinCrashError):
    """Raised when the specified dump file does not exist"""


class DebuggerNotFoundError(WinCrashError):
    """Raised when cdb.exe cannot be located on the system PATH"""


class DebuggerError(WinCrashError):
    """Failures during cdb.exe or WinDbg execution"""


# Backwards-compatible alias.
DebuggerEngineError = DebuggerError


class SymbolMismatchError(DebuggerError):
    """Raised when the .pdb GUID does not match the .dmp"""


class AIBackendError(WinCrashError):
    """API timeouts, rate limits, or safety blocks"""


class ProviderCallbackError(WinCrashError):
    """Raised if the JS Provider fails to POST back to windbg_server"""


class StorageBackendError(WinCrashError):
    """Raised when a storage backend encounters an error"""


# Backwards-compatible alias.
StorageError = StorageBackendError
