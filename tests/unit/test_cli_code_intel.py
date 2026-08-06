"""Unit tests for the ``aegis code-intel check`` CLI command.

This command is the operator-facing smoke test for the OpenClaude composition
factory (:func:`aegis_swr.openclaude.composition.build_code_agent`). It replaces
the former standalone ``python -m aegis_swr.app`` entry point, folding that
capability into the single ``aegis`` CLI composition surface.

The real gRPC client is swapped for a fake injected into the ``composition``
module so no socket is ever opened and no subprocess is ever spawned; external
mode (``auto_start`` false, the default) only ever calls ``health_check``.
"""

from __future__ import annotations

import re

import pytest
import typer.testing

import aegis_swr.openclaude.composition as composition_mod
from aegis_swr.cli.commands import app
from aegis_swr.openclaude.config import OpenClaudeSettings

runner = typer.testing.CliRunner()

_GRPC_URL = "localhost:50051"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _clean(text: str) -> str:
    """Strip ANSI colour codes and collapse whitespace/newlines rich may insert."""
    return re.sub(r"\s+", " ", _ANSI.sub("", text))


class _FakeClient:
    """Fake :class:`OpenClaudeGrpcClient`; records health checks, refuses queries."""

    instances: list[_FakeClient] = []

    def __init__(self, settings: OpenClaudeSettings):
        """Helper that provides init for the cli code intel tests."""
        self.settings = settings
        self.health_calls = 0
        _FakeClient.instances.append(self)

    async def health_check(self) -> bool:
        """Helper that provides health check for the cli code intel tests."""
        self.health_calls += 1
        return True

    async def query(self, *args: object, **kwargs: object):  # pragma: no cover
        """Helper that provides query for the cli code intel tests."""
        raise AssertionError("query() must not be called by the check command")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure OPENCLAUDE_GRPC_URL never leaks in from the developer environment."""
    monkeypatch.delenv("OPENCLAUDE_GRPC_URL", raising=False)
    _FakeClient.instances.clear()


@pytest.fixture
def _fake_client(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    """Helper that provides fake client for the cli code intel tests."""
    monkeypatch.setattr(composition_mod, "OpenClaudeGrpcClient", _FakeClient)
    return _FakeClient


def test_check_reports_unavailable_without_grpc_url():
    """[Unit] cli code intel: With the env var unset, the command exits 0 and reports unavailability.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: with the env var unset, the command exits 0 and reports unavailability.
    """
    result = runner.invoke(app, ["code-intel", "check"])
    assert result.exit_code == 0
    assert "unavailable" in _clean(result.stdout).lower()
    # No client is constructed when no backend is registered (C4).
    assert _FakeClient.instances == []


def test_check_dry_run_registers_without_connecting(
    monkeypatch: pytest.MonkeyPatch, _fake_client: type[_FakeClient]
):
    """[Unit] cli code intel: ``--dry-run`` (default) with the var set registers the backend, never connects.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``--dry-run`` (default) with the var set registers the backend, never connects.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", _GRPC_URL)
    result = runner.invoke(app, ["code-intel", "check"])
    assert result.exit_code == 0
    out = _clean(result.stdout).lower()
    assert "registered" in out
    assert "dry-run" in out
    # A client was built by the composition path, but never health-checked.
    assert len(_FakeClient.instances) == 1
    assert _FakeClient.instances[0].health_calls == 0


def test_check_no_dry_run_health_checks_the_sidecar(
    monkeypatch: pytest.MonkeyPatch, _fake_client: type[_FakeClient]
):
    """[Unit] cli code intel: ``--no-dry-run`` enters external mode and health-checks via the fake client.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``--no-dry-run`` enters external mode and health-checks via the fake client.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", _GRPC_URL)
    result = runner.invoke(app, ["code-intel", "check", "--no-dry-run"])
    assert result.exit_code == 0
    out = _clean(result.stdout).lower()
    assert "registered" in out
    assert "dry-run" not in out
    assert _FakeClient.instances[0].health_calls == 1


def test_check_help_lists_dry_run_flag():
    """[Unit] cli code intel: The command is discoverable with a documented ``--dry-run`` flag.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the command is discoverable with a documented ``--dry-run`` flag.
    """
    result = runner.invoke(app, ["code-intel", "check", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in _clean(result.stdout)
