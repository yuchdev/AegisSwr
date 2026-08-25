"""Unconditional C2 truth-table outcome tests for the harness selection layer (Task 12.0/03).

These tests assert the two config-shape outcomes of the C2 truth table that
require **no live backend** to verify: the zero-signals case (capability
unavailable, no exception) and the multi-signal case (``HarnessConfigError``
at construction time, fail loud). Both exercise pure settings-shape behaviour
via ``monkeypatch`` and run unconditionally — they are not behind
:func:`~tests.integration.harness.conftest.require_single_live_backend`.

Placing them in the integration suite rather than the unit suite is for topical
cohesion with the live smoke test; the assertions themselves are hermetic and do
not depend on any running process or sidecar.
"""

from __future__ import annotations

import pytest

from aegis_swr.harness.config import HarnessSettings
from aegis_swr.harness.exceptions import HarnessConfigError


def test_zero_signals_is_capability_unavailable(monkeypatch: pytest.MonkeyPatch):
    """[Integration] harness selection: Selector unset and zero signals → active_backend is None, no exception.

    Scenario: all four presence-signal environment variables are cleared;
    HarnessSettings() must construct without error and active_backend must be
    None — the capability-unavailable row of the C2 truth table.

    Boundaries: scoped to this test case; monkeypatch restores env after.

    On failure, first check: verify no presence-signal env var is still set
    after monkeypatching and that HarnessSettings reads signals only from the
    already-constructed nested settings objects.
    """
    for var in (
        "AEGIS_CODE_INTEL_BACKEND",
        "OPENCLAUDE_GRPC_URL",
        "CLAUDE_CODE_ENABLED",
        "OPENHANDS_SERVER_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    settings = HarnessSettings()
    assert settings.active_backend is None  # capability unavailable; no exception raised


def test_multiple_signals_raise_harness_config_error(monkeypatch: pytest.MonkeyPatch):
    """[Integration] harness selection: Selector unset and more than one signal → HarnessConfigError (C2).

    Scenario: AEGIS_CODE_INTEL_BACKEND is cleared and two presence signals are
    set simultaneously; HarnessSettings() must raise HarnessConfigError at
    construction time — fail loud, never silently pick one.

    Boundaries: scoped to this test case; monkeypatch restores env after.

    On failure, first check: verify the two env vars are valid for their
    respective backends (OPENCLAUDE_GRPC_URL accepts bare host:port;
    OPENHANDS_SERVER_URL requires an http(s)://host URL) and that
    HarnessSettings._reject_ambiguous_selection is reachable.
    """
    monkeypatch.delenv("AEGIS_CODE_INTEL_BACKEND", raising=False)
    # Use OpenClaude (bare host:port) and OpenHands (http URL) signals to trigger
    # ambiguity without setting CLAUDE_CODE_ENABLED=true, which would also require
    # CLAUDE_CODE_SCRATCH_CWD to be set and could crash ClaudeCodeSettings construction.
    monkeypatch.delenv("CLAUDE_CODE_ENABLED", raising=False)
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://localhost:3000")
    with pytest.raises(HarnessConfigError):
        HarnessSettings()  # construction-time ambiguity; never a silent pick
