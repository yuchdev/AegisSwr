"""Configuration surface for the Claude Code (``claude`` CLI) backend.

This package hosts :class:`~aegis_swr.claude_code.config.ClaudeCodeSettings`, the
environment-sourced settings for the host-permission Claude Code backend
(milestone 0005, Task 02.0). The subprocess tool, argv construction, and auth
probe land in later tasks; this package is configuration-only for now.

Nothing is re-exported at package-import time: callers import
:class:`ClaudeCodeSettings` (and the forward-declared ``ClaudeCodeConfigError``)
from :mod:`aegis_swr.claude_code.config` directly, so this package does not pull
any heavy dependency into its namespace.
"""

from __future__ import annotations
