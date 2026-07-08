"""Unit tests for :mod:`aegis_swr.router.exceptions` hierarchy.

Verifies the subclass relationships mandated by roadmap 0003 subtask 03 and the
context attributes stored on :class:`AllProvidersExhausted`.
"""

from __future__ import annotations

from aegis_swr.router.exceptions import (
    AllProvidersExhausted,
    ConfigValidationError,
    RouterException,
)


def test_all_providers_exhausted_is_router_exception() -> None:
    """AllProvidersExhausted is a subclass of RouterException."""
    assert issubclass(AllProvidersExhausted, RouterException)


def test_config_validation_error_is_not_router_exception() -> None:
    """ConfigValidationError is a separate hierarchy, not RouterException."""
    assert not issubclass(ConfigValidationError, RouterException)


def test_all_providers_exhausted_stores_context() -> None:
    """The exception stores role/tried/errors and builds a message."""
    tried = ["anthropic/claude-sonnet-4-6", "deepseek/deepseek-chat"]
    errors = ["timeout", "429 rate limit"]

    exc = AllProvidersExhausted(role="primary_reasoning", tried=tried, errors=errors)

    assert exc.role == "primary_reasoning"
    assert exc.tried == tried
    assert exc.errors == errors
    message = str(exc)
    assert "primary_reasoning" in message
    assert "deepseek/deepseek-chat" in message
    assert "429 rate limit" in message
