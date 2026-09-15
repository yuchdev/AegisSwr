"""Sample file demonstrating X012 Type1 | Type2 union annotation violation."""
from typing import Optional


def func_with_union(value: int | float) -> str:  # X012 – int | float param
    """Accept an optional integer or float and return its string representation."""
    if value is None:
        return "none"
    return str(value)
