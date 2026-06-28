"""Sample file demonstrating X006 local import violation."""


def func_with_local_import() -> str:
    """Trigger X006 by performing an import inside a function body."""
    import os  # X006 – local import
    return os.getcwd()
