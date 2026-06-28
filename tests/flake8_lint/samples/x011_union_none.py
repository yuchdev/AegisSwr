"""Sample file demonstrating X011 Type | None union annotation violation."""
from typing import Optional


def func_with_union_none(value: int | None) -> str:  # X011 – int | None param
    """Accept an optional integer and return its string representation."""
    if value is None:
        return "none"
    return str(value)
