"""Sample file demonstrating X004 muted exception handler violation."""


def func_with_muted_exception():
    """Trigger X004 by silently swallowing an exception with pass."""
    try:
        x = int("not a number")
    except ValueError:  # X004 – muted exception (pass only)
        pass
