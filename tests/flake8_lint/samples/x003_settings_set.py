"""Sample file demonstrating X003 Settings.set() violation."""


class Settings:
    """Configuration settings class."""

    def set(self, key, value):  # X003 – forbidden Settings.set method
        """Store a setting value by key."""
        self._data = {key: value}
