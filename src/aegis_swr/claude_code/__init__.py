"""Public API for the Claude Code (``claude`` CLI) backend package.

Re-exports the payload-free, dependency-free event and exception types so callers
can ``from aegis_swr.claude_code import ClaudeCodeCompleted`` without a full
module path - mirroring :mod:`aegis_swr.openclaude`.

Registration of the ``claude_code.*`` events with the
:class:`~aegis_swr.core.events.EventBus` is implicit: the bus distributes any
:class:`~aegis_swr.core.events.DomainEvent` subclass and subscribers filter on
the ``event_type`` sentinel, so there is no imperative ``bus.register(...)`` call
and :mod:`aegis_swr.core.events` is left untouched (contract C10).

:class:`~aegis_swr.claude_code.config.ClaudeCodeSettings` is deliberately **not**
re-exported here: importing it at package-import time would pull ``pydantic`` /
``pydantic_settings`` into the package namespace and break the C3 isolation
posture. It stays behind :mod:`aegis_swr.claude_code.config` and is constructed
at the composition root. The event/exception modules re-exported here are
dependency-free leaf modules (no ``pydantic``, no client library).
"""

from __future__ import annotations

from aegis_swr.claude_code.events import (
    ClaudeCodeAuthFailed,
    ClaudeCodeCompleted,
    ClaudeCodeError,
    ClaudeCodeExited,
    ClaudeCodePermissionDenied,
    ClaudeCodeSpawned,
    ClaudeCodeToolCall,
    ClaudeCodeToolResult,
)
from aegis_swr.claude_code.exceptions import (
    ClaudeCodeConfigError,
    ClaudeCodeUnavailableError,
    PermissionDeniedError,
)

__all__ = [
    # events (C10 taxonomy)
    "ClaudeCodeSpawned",
    "ClaudeCodeExited",
    "ClaudeCodeToolCall",
    "ClaudeCodeToolResult",
    "ClaudeCodePermissionDenied",
    "ClaudeCodeAuthFailed",
    "ClaudeCodeCompleted",
    "ClaudeCodeError",
    # exceptions
    "ClaudeCodeConfigError",
    "ClaudeCodeUnavailableError",
    "PermissionDeniedError",
]
