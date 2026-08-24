"""Unit tests for the harness exception hierarchy (Milestone 0005, Task 01.0.03).

Guards the two typed errors the C2 truth table distinguishes:
:class:`HarnessConfigError` (construction-time config-shape ambiguity, a
``ValueError``) and :class:`HarnessUnavailableError` (composition-time runtime
capability failure, a plain ``Exception``). Covers their base classes, the
two-independent-hierarchies invariant, attribute exposure, payload-free
construction (C13), and the leaf-module import-purity invariant (imports only
``typing`` - nothing from ``aegis_swr.*``/``grpc``/``pydantic``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aegis_swr.harness import exceptions
from aegis_swr.harness.exceptions import HarnessConfigError, HarnessUnavailableError


def test_both_types_present_with_expected_bases():
    """[Unit] exceptions: Both harness errors exist with the C2-mandated base classes.

    Scenario: HarnessConfigError subclasses ValueError; HarnessUnavailableError subclasses Exception.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: both errors exist with the expected ValueError/Exception bases.
    """
    assert issubclass(HarnessConfigError, ValueError)
    assert issubclass(HarnessUnavailableError, Exception)


def test_neither_subclasses_the_other():
    """[Unit] exceptions: The two errors are independent hierarchies (neither subclasses the other, C2).

    Scenario: both issubclass directions between the two error types are False.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: neither error subclasses the other in either direction.
    """
    assert not issubclass(HarnessUnavailableError, HarnessConfigError)
    assert not issubclass(HarnessConfigError, HarnessUnavailableError)


def test_config_error_exposes_reason_signals_and_default_field():
    """[Unit] exceptions: HarnessConfigError exposes reason/signals and defaults field to ``backend``.

    Scenario: constructed with a reason and a two-element signals frozenset.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: reason/signals are stored and field defaults to ``backend``.
    """
    signals = frozenset({"openclaude", "claude_code"})
    err = HarnessConfigError("selector unset with multiple signals", signals=signals)
    assert err.reason == "selector unset with multiple signals"
    assert err.signals == signals
    assert err.field == "backend"
    assert isinstance(err, ValueError)


def test_config_error_message_and_custom_field():
    """[Unit] exceptions: HarnessConfigError formats the canonical message and honours a custom field.

    Scenario: constructed with an explicit field name overrides the default.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the message uses the given field and reason.
    """
    err = HarnessConfigError("unrecognised family", field="selector")
    assert err.field == "selector"
    assert err.signals is None
    assert str(err) == "HarnessSettings.selector: unrecognised family"


def test_config_error_is_catchable_as_valueerror():
    """[Unit] exceptions: HarnessConfigError is caught by ``except ValueError`` (Pydantic contract).

    Scenario: raising the error is caught by a ValueError handler.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the error propagates as a ValueError subclass.
    """
    with pytest.raises(ValueError):
        raise HarnessConfigError("boom")


def test_unavailable_error_exposes_backend_and_default_signals():
    """[Unit] exceptions: HarnessUnavailableError exposes backend and defaults signals to empty frozenset.

    Scenario: constructed with only the selected backend family name.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: backend is stored and signals defaults to an empty frozenset.
    """
    err = HarnessUnavailableError("claude_code")
    assert err.backend == "claude_code"
    assert err.signals == frozenset()
    assert isinstance(err, Exception)


def test_unavailable_error_stores_provided_signals():
    """[Unit] exceptions: HarnessUnavailableError records the diagnostic signal names it is given.

    Scenario: constructed with an explicit signals frozenset.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the provided signals frozenset is stored verbatim.
    """
    signals = frozenset({"openclaude"})
    err = HarnessUnavailableError("claude_code", signals=signals)
    assert err.signals == signals
    assert "openclaude" in str(err)


def test_config_error_str_contains_no_variable_value():
    """[Unit] exceptions: HarnessConfigError.str() never embeds a variable value, secret, or payload (C13).

    Scenario: a payload-bearing string is passed only as a signal name context, never as a value.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: only field/reason/signal names reach the message, no variable value.
    """
    payload = "URL=https://secret.internal?token=abcd1234 dump 0xdeadbeef"
    err = HarnessConfigError(
        "selector unset with multiple signals",
        signals=frozenset({"openclaude", "claude_code"}),
    )
    rendered = str(err)
    assert payload not in rendered
    # Only the payload-free field, reason, and signal names appear.
    assert rendered == "HarnessSettings.backend: selector unset with multiple signals"


def test_unavailable_error_str_contains_no_variable_value():
    """[Unit] exceptions: HarnessUnavailableError.str() never embeds a value, token, or payload (C13).

    Scenario: the message lists only the backend name and sorted signal names.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no variable value, token, or payload text is in the message.
    """
    payload = "TOKEN=abcd1234 in dump 0xdeadbeef"
    err = HarnessUnavailableError("claude_code", signals=frozenset({"openclaude"}))
    rendered = str(err)
    assert payload not in rendered
    assert "claude_code" in rendered
    assert "openclaude" in rendered


def test_module_is_import_leaf():
    """[Unit] exceptions: The module imports only ``typing`` - no ``aegis_swr.*``/``grpc``/``pydantic`` (leaf).

    Scenario: AST-parse the module source and inspect every import statement.

    Boundaries: scoped to the static import graph of exceptions.py.

    On failure, first check: an import of a forbidden module was added to the leaf module.
    """
    source = Path(exceptions.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        # Ignore ``from __future__ import annotations``; capture real modules.
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    imported_roots.discard("__future__")

    assert imported_roots == {"typing"}
    assert "aegis_swr" not in imported_roots
    assert "grpc" not in imported_roots
    assert "pydantic" not in imported_roots
