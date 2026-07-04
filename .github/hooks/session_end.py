#!/usr/bin/env python3
"""SessionEnd hook - audit session completion."""
from __future__ import annotations

from _common import allow, append_log, read_event


def main() -> None:
    event = read_event()
    reason = str(event.get("reason", "unknown"))
    append_log("session.log", f"ended reason={reason}")
    allow()


if __name__ == "__main__":
    main()
