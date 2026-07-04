#!/usr/bin/env python3
"""ErrorOccurred hook - audit runtime errors."""
from __future__ import annotations

from _common import allow, append_log, read_event


def main() -> None:
    event = read_event()
    error = event.get("error", {})
    if isinstance(error, dict):
        name = str(error.get("name", "Error"))
        message = str(error.get("message", "")).replace("\n", " ").strip()
    else:
        name = "Error"
        message = str(error).replace("\n", " ").strip()
    context = str(event.get("error_context", event.get("errorContext", "unknown")))
    append_log("errors.log", f"{context} {name}: {message[:240]}")
    allow()


if __name__ == "__main__":
    main()
