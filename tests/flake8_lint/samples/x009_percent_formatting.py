"""Sample file demonstrating X009 percent-style string formatting violation."""


def func_with_percent_format(name: str) -> str:
    """Format a greeting using old-style percent formatting."""
    return "Hello %s" % name  # X009 – percent formatting
