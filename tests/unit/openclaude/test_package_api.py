"""Package-level API and C3-isolation tests for ``aegis_swr.openclaude``.

Scenario: the top-level package re-exports the seven ``openclaude.*`` events and
the three exception types for discoverability, while keeping the ``grpc``-bound
classes behind their submodules so ``import aegis_swr.openclaude`` never pulls
``grpc`` into the namespace (contract C3).
Boundaries: unit — no I/O, no process, no gRPC channel.
On failure: a re-export drifted, or a ``grpc``-touching module leaked into the
package import chain (C3 violation).
"""

from __future__ import annotations

import importlib
import sys

import pytest

_EVENT_NAMES = [
    "OpenClaudeConnected",
    "OpenClaudeDisconnected",
    "OpenClaudeToolCall",
    "OpenClaudeToolResult",
    "OpenClaudePermissionDenied",
    "OpenClaudeStreamCompleted",
    "OpenClaudeStreamError",
]
_EXCEPTION_NAMES = [
    "OpenClaudeUnavailableError",
    "PermissionDeniedError",
    "OpenClaudeConfigError",
]


@pytest.mark.parametrize("name", _EVENT_NAMES + _EXCEPTION_NAMES)
def test_public_symbol_resolves_from_top_level(name: str) -> None:
    """[Unit] package api: Each of the ten public symbols resolves from ``aegis_swr.openclaude``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: each of the ten public symbols resolves from ``aegis_swr.openclaude``.
    """
    package = importlib.import_module("aegis_swr.openclaude")
    assert hasattr(package, name), f"{name} is not re-exported"


def test_all_lists_exactly_the_public_symbols() -> None:
    """[Unit] package api: ``__all__`` names all seven events and all three exceptions, nothing more.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``__all__`` names all seven events and all three exceptions, nothing more.
    """
    package = importlib.import_module("aegis_swr.openclaude")
    assert set(package.__all__) == set(_EVENT_NAMES + _EXCEPTION_NAMES)


def test_reexports_are_the_canonical_objects() -> None:
    """[Unit] package api: Re-exported symbols are identical to their defining-module objects.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: re-exported symbols are identical to their defining-module objects.
    """
    package = importlib.import_module("aegis_swr.openclaude")
    events = importlib.import_module("aegis_swr.openclaude.events")
    exceptions = importlib.import_module("aegis_swr.openclaude.exceptions")
    for name in _EVENT_NAMES:
        assert getattr(package, name) is getattr(events, name)
    for name in _EXCEPTION_NAMES:
        assert getattr(package, name) is getattr(exceptions, name)


def test_grpc_bound_classes_not_reexported_at_top_level() -> None:
    """[Unit] package api: C3: the ``grpc``-touching classes are not importable from the package root.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: c3: the ``grpc``-touching classes are not importable from the package root.
    """
    package = importlib.import_module("aegis_swr.openclaude")
    for name in ("OpenClaudeTool", "OpenClaudeProcess", "OpenClaudeGrpcClient"):
        assert not hasattr(package, name), f"{name} must not be re-exported (C3)"


def test_importing_package_pulls_in_no_grpc() -> None:
    """[Unit] package api: C3: ``import aegis_swr.openclaude`` leaves ``grpc`` out of ``sys.modules``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: c3: ``import aegis_swr.openclaude`` leaves ``grpc`` out of ``sys.modules``.
    """
    snapshot = {
        mod: sys.modules[mod]
        for mod in list(sys.modules)
        if mod == "grpc" or mod.startswith("grpc.") or mod.startswith("aegis_swr.openclaude")
    }
    for mod in snapshot:
        del sys.modules[mod]
    try:
        importlib.import_module("aegis_swr.openclaude")
        assert "grpc" not in sys.modules, "importing aegis_swr.openclaude pulled in grpc (C3 violation)"
    finally:
        # Restore the pre-test registry verbatim: drop anything this test imported,
        # then reinstate the original module objects.
        for mod in list(sys.modules):
            if mod == "grpc" or mod.startswith("grpc.") or mod.startswith("aegis_swr.openclaude"):
                del sys.modules[mod]
        sys.modules.update(snapshot)
