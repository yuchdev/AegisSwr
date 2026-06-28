"""Sample file demonstrating X010 suppressed ImportError violation."""

try:
    import some_optional_module  # X010 – suppressed ImportError
except ImportError:
    some_optional_module = None  # type: ignore[assignment]
