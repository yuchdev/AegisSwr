"""Sample file demonstrating X002 broad Exception violation."""


def func_with_broad_exception():
    """Trigger X002 by catching the base Exception class."""
    try:
        x = 1
    except Exception:  # X002 – broad Exception
        print(f"caught: {x}")
