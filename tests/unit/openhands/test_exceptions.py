"""Unit tests for the canonical OpenHands exception hierarchy (Task 09.0.02).

Guards the three exception types, the superset
:class:`OpenHandsUnavailableError` constructor Task 08.0's ``delegate()`` branches
on via ``retriable``, the ``config.py`` re-export identity, the separation from
``HarnessConfigError`` / the router ``ConfigValidationError`` / the sibling
backends' error types, payload-free construction (C13), and the leaf-module
invariant that importing the module pulls in no HTTP/WS client library (C3).
"""

from __future__ import annotations

import importlib
import sys

import pytest

from aegis_swr.claude_code.exceptions import PermissionDeniedError as ClaudeCodePermissionDeniedError
from aegis_swr.harness.exceptions import HarnessConfigError
from aegis_swr.openclaude.exceptions import PermissionDeniedError as OpenClaudePermissionDeniedError
from aegis_swr.openhands import config as openhands_config
from aegis_swr.openhands import exceptions
from aegis_swr.openhands.exceptions import (
    OpenHandsConfigError,
    OpenHandsUnavailableError,
    PermissionDeniedError,
)
from aegis_swr.router.exceptions import ConfigValidationError


def test_three_types_present_with_expected_bases():
    """[Unit] exceptions: All three types exist as independent hierarchies subclassing Exception/ValueError.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: all three types exist as independent hierarchies subclassing Exception/ValueError.
    """
    assert issubclass(OpenHandsUnavailableError, Exception)
    assert issubclass(PermissionDeniedError, Exception)
    assert issubclass(OpenHandsConfigError, ValueError)
    # None subclasses another - three independent hierarchies.
    assert not issubclass(OpenHandsUnavailableError, PermissionDeniedError)
    assert not issubclass(PermissionDeniedError, OpenHandsUnavailableError)
    assert not issubclass(OpenHandsConfigError, OpenHandsUnavailableError)
    assert not issubclass(OpenHandsConfigError, PermissionDeniedError)


def test_unavailable_error_narrow_construction():
    """[Unit] exceptions: The narrow ``(message, server_url)`` form works with retriable defaulting True.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the narrow ``(message, server_url)`` form works with retriable defaulting True.
    """
    err = OpenHandsUnavailableError("sidecar unreachable", "http://localhost:3000")
    assert str(err) == "sidecar unreachable"
    assert err.server_url == "http://localhost:3000"
    assert err.retriable is True
    assert err.status_code is None


def test_unavailable_error_superset_kwargs_delegate_contract():
    """[Unit] exceptions: Task 08.0's contract: keyword-only ``retriable``/``status_code`` are stored.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: keyword-only ``retriable``/``status_code`` are stored for delegate() to branch on.
    """
    err = OpenHandsUnavailableError(
        "OpenHands REST/WS transport failed",
        retriable=False,
        status_code="503",
    )
    assert err.server_url is None
    assert err.retriable is False
    assert err.status_code == "503"


def test_unavailable_error_defaults():
    """[Unit] exceptions: Constructed with only a message, server_url is None and retriable defaults True.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: constructed with only a message, server_url is None and retriable defaults True.
    """
    err = OpenHandsUnavailableError("unreachable")
    assert err.server_url is None
    assert err.retriable is True
    assert err.status_code is None


def test_permission_denied_error_shape():
    """[Unit] exceptions: PermissionDeniedError stores action/binary, is non-retriable, formats a fixed message.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: PermissionDeniedError stores action/binary, is non-retriable, formats a fixed message.
    """
    err = PermissionDeniedError(action="run", denied_binary="curl")
    assert err.action == "run"
    assert err.denied_binary == "curl"
    assert err.retriable is False
    assert PermissionDeniedError.retriable is False
    assert str(err) == ("OpenHands requested non-allowlisted command 'curl' via action 'run'; denied (non-retriable).")


def test_config_error_message_and_fields():
    """[Unit] exceptions: OpenHandsConfigError stores field/reason and formats the canonical message.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: OpenHandsConfigError stores field/reason and formats the canonical message.
    """
    err = OpenHandsConfigError(field="server_url", reason="value must be an http(s)://host[:port] URL")
    assert err.field == "server_url"
    assert err.reason == "value must be an http(s)://host[:port] URL"
    assert str(err) == "OpenHandsSettings.server_url: value must be an http(s)://host[:port] URL"
    assert isinstance(err, ValueError)


def test_config_error_is_catchable_as_valueerror():
    """[Unit] exceptions: OpenHandsConfigError is caught by ``except ValueError`` (Pydantic contract).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: OpenHandsConfigError is caught by ``except ValueError`` (Pydantic contract).
    """
    with pytest.raises(ValueError):
        raise OpenHandsConfigError(field="f", reason="r")


def test_config_reexport_identity():
    """[Unit] exceptions: ``config.OpenHandsConfigError`` is the same object as the canonical class.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``config.OpenHandsConfigError`` is the same object as the canonical class.
    """
    assert openhands_config.OpenHandsConfigError is OpenHandsConfigError


def test_config_error_distinct_from_harness_and_router_errors():
    """[Unit] exceptions: OpenHandsConfigError never subclasses HarnessConfigError or router ConfigValidationError.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: OpenHandsConfigError is a distinct type from the harness and router config errors.
    """
    assert not issubclass(OpenHandsConfigError, HarnessConfigError)
    assert not issubclass(HarnessConfigError, OpenHandsConfigError)
    assert not issubclass(OpenHandsConfigError, ConfigValidationError)
    assert not issubclass(ConfigValidationError, OpenHandsConfigError)
    assert OpenHandsConfigError is not HarnessConfigError
    assert OpenHandsConfigError is not ConfigValidationError


def test_permission_denied_distinct_from_sibling_backends():
    """[Unit] exceptions: OpenHands' PermissionDeniedError is a distinct class from the sibling backends'.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the per-backend PermissionDeniedError classes are distinct and unrelated (C3).
    """
    assert PermissionDeniedError is not OpenClaudePermissionDeniedError
    assert PermissionDeniedError is not ClaudeCodePermissionDeniedError
    assert not issubclass(PermissionDeniedError, OpenClaudePermissionDeniedError)
    assert not issubclass(OpenClaudePermissionDeniedError, PermissionDeniedError)
    assert not issubclass(PermissionDeniedError, ClaudeCodePermissionDeniedError)
    assert not issubclass(ClaudeCodePermissionDeniedError, PermissionDeniedError)
    # OpenHands keys on ``action`` where OpenClaude/Claude Code key on ``tool``.
    err = PermissionDeniedError(action="run", denied_binary="curl")
    assert hasattr(err, "action")
    assert not hasattr(err, "tool")


def test_no_payload_leakage_by_construction():
    """[Unit] exceptions: No exception embeds payload beyond the caller-provided fields (C13).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: only caller-provided fields reach a message; no extra payload is embedded.
    """
    payload = "SECRET_TOKEN=abcd1234 in dump 0xdeadbeef"

    unavailable = OpenHandsUnavailableError("transport failure", status_code="UNAVAILABLE")
    assert payload not in str(unavailable)

    # A caller who names a binary sees only that binary, not a full command line.
    permission = PermissionDeniedError(action="run", denied_binary="curl")
    assert payload not in str(permission)

    # If a caller *does* pass payload as the reason, it appears verbatim and only
    # there - the type adds nothing beyond the caller-provided field/reason.
    config_err = OpenHandsConfigError(field="server_url", reason=payload)
    assert str(config_err) == f"OpenHandsSettings.server_url: {payload}"


def test_import_pulls_in_no_client_library():
    """[Unit] exceptions: Importing the leaf exceptions module never imports an HTTP/WS client (C3).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: importing ``exceptions`` never imports ``httpx``, ``websockets``, or ``grpc`` (C3).
    """
    forbidden = ("httpx", "websockets", "grpc")
    absent_before = {name for name in forbidden if name not in sys.modules}
    reimported = importlib.import_module("aegis_swr.openhands.exceptions")
    assert reimported is exceptions
    for name in absent_before:
        assert name not in sys.modules
