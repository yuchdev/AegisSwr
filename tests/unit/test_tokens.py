"""Unit tests for :mod:`aegis_swr.core.tokens`."""

from __future__ import annotations

from requests import RequestException

from aegis_swr.core import tokens


def test_count_tokens_falls_back_when_encoder_unavailable(monkeypatch):
    """[Unit] tokens: count_tokens falls back to the chars-per-token heuristic when encoder init fails.

    Scenario: ``tiktoken.get_encoding()`` raises an offline-style initialization error.

    Boundaries: monkeypatched ``tiktoken`` lookup plus the cached ``tokens._encoder`` helper.

    On failure, first check: the patched exception type is still covered and the fallback returns ``len(text) // 4``.
    """

    def _boom(_name: str):
        """Raise the offline-style initialization failure used by this test."""
        raise OSError("offline")

    monkeypatch.setattr(tokens.tiktoken, "get_encoding", _boom)
    tokens._encoder.cache_clear()
    try:
        assert tokens.count_tokens("x" * 20) == 5
    finally:
        tokens._encoder.cache_clear()


def test_truncate_to_tokens_falls_back_when_encoder_unavailable(monkeypatch):
    """[Unit] tokens: truncate_to_tokens uses the chars-per-token fallback when encoder init fails.

    Scenario: ``tiktoken.get_encoding()`` raises a network-style initialization error before tokenization.

    Boundaries: monkeypatched ``tiktoken`` lookup plus the cached ``tokens._encoder`` helper.

    On failure, first check: the patched exception type is still covered and truncation uses ``limit * 4`` characters.
    """

    def _boom(_name: str):
        """Raise the network-style initialization failure used by this test."""
        raise RequestException("unavailable")

    monkeypatch.setattr(tokens.tiktoken, "get_encoding", _boom)
    tokens._encoder.cache_clear()
    try:
        out, was_truncated = tokens.truncate_to_tokens("x" * 40, limit=5)
        assert was_truncated is True
        assert out == "x" * 20
    finally:
        tokens._encoder.cache_clear()
