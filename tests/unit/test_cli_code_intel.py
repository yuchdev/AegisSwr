"""Unit tests for the backend-agnostic ``aegis code-intel check`` CLI command.

This command is the operator-facing smoke test for the harness composition
factory (:func:`aegis_swr.harness.composition.build_code_agent`). It reports
**which** backend is active - or that the capability is unavailable - for every
C2 selection outcome, and for ``claude_code`` additionally reports the resolved
auth mode (never a credential, C7/C13).

Every external seam is faked: the OpenClaude gRPC client is swapped for a fake
injected into the ``harness.composition`` module so no socket is opened, and no
test spawns ``claude``, starts a sidecar, or requires Docker.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import typer.testing

import aegis_swr.harness.composition as composition_mod
from aegis_swr.cli.commands import app
from aegis_swr.openclaude.config import OpenClaudeSettings

runner = typer.testing.CliRunner()

_GRPC_URL = "localhost:50051"
_SERVER_URL = "http://localhost:3000"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _clean(text: str) -> str:
    """Strip ANSI colour codes and collapse whitespace/newlines rich may insert."""
    return re.sub(r"\s+", " ", _ANSI.sub("", text))


class _FakeClient:
    """Fake :class:`OpenClaudeGrpcClient`; records health checks, refuses queries."""

    instances: list[_FakeClient] = []

    def __init__(self, settings: OpenClaudeSettings):
        """Record construction from ``settings``; open no channel."""
        self.settings = settings
        self.health_calls = 0
        _FakeClient.instances.append(self)

    async def health_check(self) -> bool:
        """Report healthy so external-mode entry succeeds without a socket."""
        self.health_calls += 1
        return True

    async def query(self, *args: object, **kwargs: object):  # pragma: no cover
        """Refuse queries; the check command never delegates."""
        raise AssertionError("query() must not be called by the check command")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    """Clear every harness signal/selector and credential so nothing leaks in."""
    for var in (
        "AEGIS_CODE_INTEL_BACKEND",
        "OPENCLAUDE_GRPC_URL",
        "CLAUDE_CODE_ENABLED",
        "CLAUDE_CODE_SCRATCH_CWD",
        "CLAUDE_CODE_AUTH_MODE",
        "OPENHANDS_SERVER_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    _FakeClient.instances.clear()


@pytest.fixture
def _fake_client(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    """Swap the real gRPC client for the fake inside the ``composition`` module."""
    monkeypatch.setattr(composition_mod, "OpenClaudeGrpcClient", _FakeClient)
    return _FakeClient


def test_check_reports_unavailable_without_any_signal():
    """[Unit] cli code intel: with no presence signal the command exits 0 and reports unavailability.

    Scenario: no harness signal or selector is set and ``check`` is invoked.

    Boundaries: scoped to the C2 ``None`` selection outcome.

    On failure, first check: the command exits 0 and reports no backend active.
    """
    result = runner.invoke(app, ["code-intel", "check"])
    assert result.exit_code == 0
    out = _clean(result.stdout).lower()
    assert "unavailable" in out
    assert "no backend active" in out
    assert _FakeClient.instances == []


def test_check_dry_run_openclaude_reports_active(monkeypatch: pytest.MonkeyPatch, _fake_client: type[_FakeClient]):
    """[Unit] cli code intel: OPENCLAUDE_GRPC_URL set + dry-run reports openclaude active, never connects.

    Scenario: only ``OPENCLAUDE_GRPC_URL`` is set and ``--dry-run`` (default) runs.

    Boundaries: scoped to the OpenClaude single-signal auto-select outcome.

    On failure, first check: output names ``openclaude`` active and the fake is never health-checked.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", _GRPC_URL)
    result = runner.invoke(app, ["code-intel", "check"])
    assert result.exit_code == 0
    out = _clean(result.stdout).lower()
    assert "backend active: openclaude" in out
    assert "dry-run" in out
    assert len(_FakeClient.instances) == 1
    assert _FakeClient.instances[0].health_calls == 0


def test_check_no_dry_run_openclaude_health_checks(monkeypatch: pytest.MonkeyPatch, _fake_client: type[_FakeClient]):
    """[Unit] cli code intel: ``--no-dry-run`` enters external mode and health-checks the fake client.

    Scenario: ``OPENCLAUDE_GRPC_URL`` is set and ``--no-dry-run`` runs.

    Boundaries: scoped to the OpenClaude sidecar lifecycle via the injected fake.

    On failure, first check: output names ``openclaude`` active and the fake is health-checked once.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", _GRPC_URL)
    result = runner.invoke(app, ["code-intel", "check", "--no-dry-run"])
    assert result.exit_code == 0
    out = _clean(result.stdout).lower()
    assert "backend active: openclaude" in out
    assert "dry-run" not in out
    assert _FakeClient.instances[0].health_calls == 1


def test_check_claude_code_reports_auth_mode_not_credential(monkeypatch: pytest.MonkeyPatch, tmp_path: Any):
    """[Unit] cli code intel: an enabled Claude Code backend reports its auth mode and no credential.

    Scenario: Claude Code is enabled with ``auth_mode=api_key`` and ``check`` runs.

    Boundaries: scoped to the C7 auth-mode reporting for the ``claude_code`` outcome.

    On failure, first check: output names ``claude_code`` and its auth mode, never a token value.
    """
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")
    monkeypatch.setenv("CLAUDE_CODE_SCRATCH_CWD", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_AUTH_MODE", "api_key")
    result = runner.invoke(app, ["code-intel", "check"])
    assert result.exit_code == 0
    out = _clean(result.stdout)
    assert "backend active: claude_code" in out.lower()
    assert "auth mode: api_key" in out.lower()
    # The auth MODE is a non-secret enum; no credential value ever appears (C13).
    assert "ANTHROPIC" not in out.upper()


def test_check_ambiguous_config_exits_with_config_error(monkeypatch: pytest.MonkeyPatch):
    """[Unit] cli code intel: two signals with no selector surface a config error and a distinct exit code.

    Scenario: two presence signals are set with no explicit selector.

    Boundaries: scoped to the C2 ambiguity (``HarnessConfigError``) construction path.

    On failure, first check: exit code is 2, a config error is reported, and no URL value leaks.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", _GRPC_URL)
    monkeypatch.setenv("OPENHANDS_SERVER_URL", _SERVER_URL)
    result = runner.invoke(app, ["code-intel", "check"])
    assert result.exit_code == 2
    out = _clean(result.stdout).lower()
    assert "configuration error" in out
    assert _GRPC_URL not in out
    assert _SERVER_URL not in out


def test_check_explicit_backend_absent_signal_exits_unavailable(monkeypatch: pytest.MonkeyPatch):
    """[Unit] cli code intel: an explicit backend whose signal is absent exits non-zero as unavailable.

    Scenario: ``AEGIS_CODE_INTEL_BACKEND=claude_code`` is set but the backend is not enabled.

    Boundaries: scoped to the C2 explicit-selector-absent (``HarnessUnavailableError``) path.

    On failure, first check: exit code is 1 and the output reports the backend unavailable.
    """
    monkeypatch.setenv("AEGIS_CODE_INTEL_BACKEND", "claude_code")
    result = runner.invoke(app, ["code-intel", "check"])
    assert result.exit_code == 1
    out = _clean(result.stdout).lower()
    assert "unavailable" in out
    assert "claude_code" in out


def test_check_help_lists_dry_run_flag():
    """[Unit] cli code intel: the command is discoverable with a documented ``--dry-run`` flag.

    Scenario: ``check --help`` is invoked.

    Boundaries: scoped to CLI option discoverability.

    On failure, first check: the help text lists the ``--dry-run`` flag.
    """
    result = runner.invoke(app, ["code-intel", "check", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in _clean(result.stdout)
