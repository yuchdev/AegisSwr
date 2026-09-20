"""Unit tests for :mod:`aegis_swr.core.tokens`."""

from __future__ import annotations

from aegis_swr.core import tokens


def test_count_tokens_falls_back_when_encoder_unavailable(monkeypatch):
    """count_tokens falls back to chars/4 heuristic when tiktoken init fails."""

    def _boom(_name: str):
        raise OSError("offline")

    monkeypatch.setattr(tokens.tiktoken, "get_encoding", _boom)
    tokens._encoder.cache_clear()
    try:
        assert tokens.count_tokens("x" * 20) == 5
    finally:
        tokens._encoder.cache_clear()


def test_truncate_to_tokens_falls_back_when_encoder_unavailable(monkeypatch):
    """truncate_to_tokens uses chars/4 fallback when tiktoken init fails."""

    def _boom(_name: str):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(tokens.tiktoken, "get_encoding", _boom)
    tokens._encoder.cache_clear()
    try:
        out, was_truncated = tokens.truncate_to_tokens("x" * 40, limit=5)
        assert was_truncated is True
        assert out == "x" * 20
    finally:
        tokens._encoder.cache_clear()
