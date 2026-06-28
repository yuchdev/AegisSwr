"""Sample file demonstrating X008 explicit None return annotation violation."""


def func_with_none_annotation() -> None:  # X008 – explicit -> None
    """Print a greeting message."""
    print("hello")
