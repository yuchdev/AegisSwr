class AegisSWRError(Exception):
    """Base exception for all Aegis SWR errors"""


class AIOutputValidationError(AegisSWRError):
    """LLM response failed schema validation after one retry"""


class PlatformNotSupportedError(AegisSWRError):
    """No debug backend is available for the current platform"""


class DebugExtractionError(AegisSWRError):
    """A debugger subprocess failed, timed out, or produced no usable output"""


class SandboxExecutionError(AegisSWRError):
    """Sandbox container failed to start or timed out"""


class IncidentNotFoundError(AegisSWRError):
    """Requested incident ID does not exist in storage"""


class CodeBackendError(AegisSWRError):
    """A code backend could not read VCS history (missing repo, binary, or failed command)"""
