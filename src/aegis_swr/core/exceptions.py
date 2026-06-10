class AegisSWRError(Exception):
    """Base exception for all Aegis SWR errors"""
    pass


class AIOutputValidationError(AegisSWRError):
    """LLM response failed schema validation after one retry"""
    pass


class PlatformNotSupportedError(AegisSWRError):
    """No debug backend is available for the current platform"""
    pass


class DebugExtractionError(AegisSWRError):
    """A debugger subprocess failed, timed out, or produced no usable output"""
    pass


class SandboxExecutionError(AegisSWRError):
    """Sandbox container failed to start or timed out"""
    pass


class IncidentNotFoundError(AegisSWRError):
    """Requested incident ID does not exist in storage"""
    pass


class CodeBackendError(AegisSWRError):
    """A code backend could not read VCS history (missing repo, binary, or failed command)"""
    pass
