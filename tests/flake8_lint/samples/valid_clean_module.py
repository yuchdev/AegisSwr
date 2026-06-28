"""A valid, clean module with no lint rule violations."""
from typing import Optional


class CleanConfig:
    """A simple read-only configuration holder."""

    def get_value(self, key: str) -> str:
        """Return the configured value for the given key."""
        return f"value_for_{key}"

    def update(self, key: str, value: str):
        """Apply a key-value update to this configuration."""
        print(f"Updating {key} = {value}")


def process_items(items: list) -> list:
    """Filter and return non-falsy items from the input list."""
    return [item for item in items if item]


def log_event(message: str):
    """Print a formatted event message to stdout."""
    print(f"Event: {message}")


def maybe_greet(name: Optional[str]) -> str:
    """Return a greeting for the given name, or a default greeting."""
    if name is None:
        return "Hello, stranger"
    return f"Hello, {name}"
