"""Sample file demonstrating X007 missing return type annotation violation."""


def func_without_return_annotation(value: str):  # X007 – no -> annotation
    """Return the uppercase form of the input string."""
    return value.upper()
