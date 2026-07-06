class AegisSWRError(Exception):
    """Base exception for all Aegis SWR errors"""

    pass


class AIOutputValidationError(AegisSWRError):
    """LLM response failed schema validation after one retry"""

    pass


class AIBackendError(AegisSWRError):
    """An AI backend call failed at the transport/API layer (timeout, auth,
    throttling, or an unexpected provider response). Carries a sanitised
    message only - never the raw provider payload or any credential."""

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


class RelationalStoreError(AegisSWRError):
    """A relational store operation failed (connection, query, or serialization error)."""

    pass


class VectorStoreError(AegisSWRError):
    """A vector store operation failed (connection, embedding, or query error)."""

    pass


class LogBackendError(AegisSWRError):
    """A log backend query failed (connection, auth, or malformed response)."""

    pass
