"""Sample file demonstrating X001 bare except violation."""


def func_with_bare_except():
    """Trigger X001 by using a bare except clause."""
    try:
        x = 1
    except:  # X001 – bare except
        print(f"caught something: {x}")
