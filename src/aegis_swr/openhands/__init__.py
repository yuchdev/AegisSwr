"""Public API for the OpenHands backend integration package.

This package holds the environment-sourced configuration for the OpenHands
code-intelligence backend (Task 06.0). Runtime classes (``OpenHandsProcess``,
``OpenHandsClient``, ``OpenHandsTool``) land in later tasks and are deliberately
**not** re-exported here so importing this package never pulls the OpenHands
HTTP/WS client library into the namespace (contract C3 isolation boundary).
"""

from __future__ import annotations
