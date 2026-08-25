"""Fixtures and skip guards for the harness selection smoke tests (Task 12.0/03).

Reuses per-backend availability predicates from the claude_code and openhands
conftest modules. Adds a single-active-backend guard
(:func:`require_single_live_backend`) that skips the live smoke module unless
exactly one backend is both signalled and available — the precondition for
well-defined auto-selection (C2).

The config-outcome test module (``test_selection_outcomes.py``) does **not** use
this guard; it runs unconditionally and asserts pure settings-shape behaviour
with no live backend required.
"""

from __future__ import annotations

import pytest

from aegis_swr.claude_code.config import ClaudeCodeSettings
from tests.integration.claude_code.conftest import (
    _api_credential_present,
    _binary_present,
    _claude_code_enabled,
)
from tests.integration.openhands.conftest import _docker_available, _server_url_set

# --------------------------------------------------------------------------- #
# Composite availability predicates
# --------------------------------------------------------------------------- #


def _live_claude_code_available() -> bool:
    """True when Claude Code could actually serve a live delegate in auto/api mode.

    Requires the presence signal, the binary, and an API credential.

    :return: Whether Claude Code is fully available for a live delegate call.
    """
    return _claude_code_enabled() and _binary_present(ClaudeCodeSettings(enabled=False)) and _api_credential_present()


def _live_openhands_available() -> bool:
    """True when OpenHands could actually serve a live delegate call.

    Requires the server URL signal and a reachable Docker daemon.

    :return: Whether OpenHands is fully available for a live delegate call.
    """
    return _server_url_set() and _docker_available()


# --------------------------------------------------------------------------- #
# Module-level guard (live smoke test only)
# --------------------------------------------------------------------------- #


def require_single_live_backend():
    """Skip unless exactly one backend is both signalled and live.

    The smoke test asserts auto-selection, which is only well-defined when a
    single presence signal is active (C2). When zero or more than one backend is
    live, this module skips — the multi-signal *rejection* path is asserted
    separately (without any live backend) in ``test_selection_outcomes.py``.
    """
    live = [
        name
        for name, ok in (
            ("claude_code", _live_claude_code_available()),
            ("openhands", _live_openhands_available()),
        )
        if ok
    ]
    if len(live) != 1:
        pytest.skip(
            f"harness smoke needs exactly one live backend, found {live!r}",
            allow_module_level=True,
        )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def active_backend_name() -> str:
    """Return the single live backend family name (guaranteed present by the guard).

    :return: ``"claude_code"`` or ``"openhands"``, whichever is live.
    """
    if _live_claude_code_available():
        return "claude_code"
    return "openhands"
