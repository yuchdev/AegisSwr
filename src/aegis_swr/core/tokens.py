"""Token counting utilities with an offline-safe fallback.

The tiktoken is a hard dependency, but its encoding files are fetched from the
network on first use and cached. In air-gapped or sandboxed environments that
fetch can fail; in that case we fall back to a conservative chars/4 heuristic, so
the pipeline never breaks on token accounting alone.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

import tiktoken

_CHARS_PER_TOKEN = 4


@lru_cache(maxsize=1)
def _encoder() -> Optional[Any]:
    """Return a tiktoken encoding instance of the most common CL100K base model."""
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def count_tokens(text: str) -> int:
    """Return the token count for ``text`` (heuristic if tiktoken is unavailable)"""
    if not text:
        return 0
    enc = _encoder()
    if enc is None:
        return max(1, len(text) // _CHARS_PER_TOKEN)
    tokens: list[int] = enc.encode(text)
    return len(tokens)


def truncate_to_tokens(text: str, limit: int) -> tuple[str, bool]:
    """Truncate ``text`` to at most ``limit`` tokens.

    Returns ``(text, was_truncated)``.
    """
    if not text:
        return text, False
    enc = _encoder()
    if enc is None:
        max_chars = limit * _CHARS_PER_TOKEN
        if len(text) <= max_chars:
            return text, False
        return text[:max_chars], True
    tokens: list[int] = enc.encode(text)
    if len(tokens) <= limit:
        return text, False
    decoded: str = enc.decode(tokens[:limit])
    return decoded, True
