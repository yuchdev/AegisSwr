#!/usr/bin/env python3
"""UserPromptSubmit hook - audit prompt submissions."""
from __future__ import annotations

from _common import allow, append_log, read_event


def main():
    event = read_event()
    prompt = str(event.get("prompt", "")).replace("\n", " ").strip()
    if prompt:
        append_log("prompts.log", prompt[:240])
    allow()


if __name__ == "__main__":
    main()
