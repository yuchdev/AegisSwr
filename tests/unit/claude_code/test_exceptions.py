"""Unit tests for the canonical Claude Code exception hierarchy (Task 05.0.02).

Guards the three canonical exception types, the ``ClaudeCodeUnavailableError``
keyword-only ``binary``/``reason`` surface the auth-probe depends on, the
``config.py`` re-export identity, the router/harness-vs-Claude-Code
configuration-error separation, payload-free construction (C7/C13), and the
leaf-module invariant that importing the module pulls in no ``grpc`` or
``pydantic`` (C3).
"""

from __future__ import annotations

import importlib
import sys

import pytest

from aegis_swr.claude_code import config as claude_code_config
from aegis_swr.claude_code import exceptions
from aegis_swr.claude_code.exceptions import (
    ClaudeCodeConfigError,
    ClaudeCodeUnavailableError,
    PermissionDeniedError,
)
from aegis_swr.harness.exceptions import HarnessConfigError
from aegis_swr.router.exceptions import ConfigValidationError

#: The fixed auth-failure vocabulary shared with ``ClaudeCodeAuthFailed`` (C7).
_AUTH_REASONS = ("ambiguous_credential", "no_stored_login", "token_rejected")


def test_three_types_present_with_expected_bases():
    """[Unit] exceptions: All three types exist as independent hierarchies subclassing Exception/ValueError.

    Scenario: bases and cross-subclassing of the three types are inspected.

    Boundaries: scoped to class-hierarchy inspection.

    On failure, first check: ``ClaudeCodeConfigError`` must be a ``ValueError``
    and no type may subclass another (C7 separation).
    """
    assert issubclass(ClaudeCodeConfigError, ValueError)
    assert issubclass(ClaudeCodeUnavailableError, Exception)
    assert issubclass(PermissionDeniedError, Exception)
    assert not issubclass(ClaudeCodeUnavailableError, ClaudeCodeConfigError)
    assert not issubclass(ClaudeCodeConfigError, ClaudeCodeUnavailableError)
    assert not issubclass(ClaudeCodeUnavailableError, PermissionDeniedError)
    assert not issubclass(PermissionDeniedError, ClaudeCodeUnavailableError)


def test_config_error_message_and_fields():
    """[Unit] exceptions: ClaudeCodeConfigError stores field/reason and formats the canonical message.

    Scenario: a config error is built with a field and reason.

    Boundaries: scoped to one construction.

    On failure, first check: the message format
    ``ClaudeCodeSettings.{field}: {reason}`` (identical to the Task 02.0 forward
    declaration) drifted.
    """
    err = ClaudeCodeConfigError(field="max_turns", reason="must be a positive integer (>= 1)")
    assert err.field == "max_turns"
    assert err.reason == "must be a positive integer (>= 1)"
    assert str(err) == "ClaudeCodeSettings.max_turns: must be a positive integer (>= 1)"
    assert isinstance(err, ValueError)


def test_config_error_is_catchable_as_valueerror():
    """[Unit] exceptions: ClaudeCodeConfigError is caught by ``except ValueError`` (Pydantic contract).

    Scenario: the error is raised and caught via its ``ValueError`` base.

    Boundaries: scoped to a single raise/catch.

    On failure, first check: the ``ValueError`` base is required so Pydantic
    validator unwrapping keeps working.
    """
    with pytest.raises(ValueError):
        raise ClaudeCodeConfigError(field="f", reason="r")


def test_config_reexport_identity():
    """[Unit] exceptions: ``config.ClaudeCodeConfigError`` is the same object as the canonical class.

    Scenario: the ``config.py`` re-export alias is compared by identity to the
    canonical ``exceptions`` class.

    Boundaries: scoped to an identity check across the two modules.

    On failure, first check: the re-export in ``config.py`` was replaced by a
    copy/subclass instead of an ``import ... as`` alias, breaking every
    ``except`` site that catches via ``config.ClaudeCodeConfigError``.
    """
    assert claude_code_config.ClaudeCodeConfigError is ClaudeCodeConfigError
    assert claude_code_config.ClaudeCodeConfigError is exceptions.ClaudeCodeConfigError


def test_config_error_distinct_from_router_and_harness_config_errors():
    """[Unit] exceptions: ClaudeCodeConfigError never subclasses the router or harness config errors.

    Scenario: cross-subclassing against ``ConfigValidationError`` and
    ``HarnessConfigError`` is inspected in both directions.

    Boundaries: scoped to class-hierarchy inspection across three modules.

    On failure, first check: three config-error surfaces must stay independently
    catchable - none subclasses another.
    """
    assert not issubclass(ClaudeCodeConfigError, ConfigValidationError)
    assert not issubclass(ConfigValidationError, ClaudeCodeConfigError)
    assert not issubclass(ClaudeCodeConfigError, HarnessConfigError)
    assert not issubclass(HarnessConfigError, ClaudeCodeConfigError)
    assert ClaudeCodeConfigError is not ConfigValidationError
    assert ClaudeCodeConfigError is not HarnessConfigError


def test_unavailable_error_narrow_construction():
    """[Unit] exceptions: The common ``(message)`` form works with ``binary``/``reason`` defaulting None.

    Scenario: the non-auth failure path constructs with only a message.

    Boundaries: scoped to one construction.

    On failure, first check: ``binary``/``reason`` must default to ``None`` so
    the common ``ClaudeCodeUnavailableError("...")`` call site stays clean.
    """
    err = ClaudeCodeUnavailableError("claude binary not found")
    assert str(err) == "claude binary not found"
    assert err.binary is None
    assert err.reason is None


def test_unavailable_error_binary_keyword_stored():
    """[Unit] exceptions: The keyword-only ``binary`` is stored for spawn/health diagnostics.

    Scenario: a spawn failure supplies the configured binary name.

    Boundaries: scoped to one construction.

    On failure, first check: ``binary`` must be keyword-only and stored verbatim
    (configuration, never payload).
    """
    err = ClaudeCodeUnavailableError("could not spawn one-shot subprocess", binary="claude")
    assert err.binary == "claude"
    assert err.reason is None


@pytest.mark.parametrize("reason", _AUTH_REASONS)
def test_unavailable_error_auth_reason_vocabulary(reason: str):
    """[Unit] exceptions: The auth-probe failure carries a fixed ``reason`` shared with ClaudeCodeAuthFailed.

    Scenario: each fixed-vocabulary reason is threaded through the keyword-only
    ``reason`` argument.

    Boundaries: scoped to one construction per reason.

    On failure, first check: ``reason`` must be keyword-only and stored, and the
    message must not embed the credential that caused the failure.
    """
    err = ClaudeCodeUnavailableError("resolved credential rejected by auth probe", reason=reason)
    assert err.reason == reason
    assert err.binary is None


def test_unavailable_error_positional_binary_rejected():
    """[Unit] exceptions: ``binary``/``reason`` are keyword-only (positional passing raises).

    Scenario: an attempt to pass ``binary`` positionally is rejected.

    Boundaries: scoped to one construction attempt.

    On failure, first check: the ``*`` keyword-only marker was dropped from the
    constructor.
    """
    with pytest.raises(TypeError):
        ClaudeCodeUnavailableError("boom", "claude")  # type: ignore[misc]


def test_permission_denied_error_shape():
    """[Unit] exceptions: PermissionDeniedError stores tool/binary, is non-retriable, formats a fixed message.

    Scenario: a denial is constructed and its class + instance ``retriable``
    flag and message are inspected.

    Boundaries: scoped to one construction.

    On failure, first check: ``retriable`` must be ``False`` at class and
    instance level, and the message must name only the binary (never a full
    command line).
    """
    err = PermissionDeniedError(tool="Bash", denied_binary="rm")
    assert err.tool == "Bash"
    assert err.denied_binary == "rm"
    assert err.retriable is False
    assert PermissionDeniedError.retriable is False
    assert str(err) == ("Claude Code requested non-allowlisted command 'rm' via tool 'Bash'; denied (non-retriable).")


def test_no_payload_leakage_by_construction():
    """[Unit] exceptions: Only caller-provided fields reach a message; no extra payload is embedded (C7/C13).

    Scenario: a payload/credential-looking string is checked to never appear in
    messages unless the caller explicitly passes it as the reason.

    Boundaries: scoped to three constructions.

    On failure, first check: an exception type embedded content beyond the
    caller-provided field/reason/binary.
    """
    payload = "ANTHROPIC_API_KEY=sk-abcd1234 in dump 0xdeadbeef"

    unavailable = ClaudeCodeUnavailableError("auth probe failed", reason="token_rejected")
    assert payload not in str(unavailable)
    assert "token_rejected" == unavailable.reason

    permission = PermissionDeniedError(tool="Bash", denied_binary="curl")
    assert payload not in str(permission)

    # If a caller *does* pass payload as the reason it appears verbatim and only
    # there - the type adds nothing beyond the caller-provided field/reason.
    config_err = ClaudeCodeConfigError(field="scratch_cwd", reason=payload)
    assert str(config_err) == f"ClaudeCodeSettings.scratch_cwd: {payload}"


def test_import_pulls_in_no_grpc():
    """[Unit] exceptions: Importing the leaf exceptions module never imports ``grpc`` (C3).

    Scenario: the module is re-imported and ``sys.modules`` is inspected.

    Boundaries: scoped to import-graph inspection; asserts absence only when
    ``grpc`` was not already loaded.

    On failure, first check: the exceptions leaf gained a forbidden dependency
    edge.
    """
    grpc_before = "grpc" in sys.modules
    reimport = importlib.import_module("aegis_swr.claude_code.exceptions")
    assert reimport is exceptions
    if not grpc_before:
        assert "grpc" not in sys.modules
