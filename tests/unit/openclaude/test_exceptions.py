"""Unit tests for the canonical OpenClaude exception hierarchy (Task 05.0.02).

Guards the three reconciled exception types, the superset
:class:`OpenClaudeUnavailableError` constructor the gRPC client depends on, the
``config.py`` re-export identity, the router-vs-OpenClaude configuration-error
separation, payload-free construction (C9), and the leaf-module invariant that
importing the module pulls in no ``grpc`` (C3).
"""

from __future__ import annotations

import sys

import pytest

from aegis_swr.openclaude import config as openclaude_config
from aegis_swr.openclaude import exceptions
from aegis_swr.openclaude.exceptions import (
    OpenClaudeConfigError,
    OpenClaudeUnavailableError,
    PermissionDeniedError,
)
from aegis_swr.router.exceptions import ConfigValidationError


def test_three_types_present_with_expected_bases() -> None:
    """All three types exist as independent hierarchies subclassing Exception/ValueError."""
    assert issubclass(OpenClaudeUnavailableError, Exception)
    assert issubclass(PermissionDeniedError, Exception)
    assert issubclass(OpenClaudeConfigError, ValueError)
    # None subclasses another - three independent hierarchies.
    assert not issubclass(OpenClaudeUnavailableError, PermissionDeniedError)
    assert not issubclass(PermissionDeniedError, OpenClaudeUnavailableError)
    assert not issubclass(OpenClaudeConfigError, OpenClaudeUnavailableError)
    assert not issubclass(OpenClaudeConfigError, PermissionDeniedError)


def test_no_legacy_openclaude_error_base() -> None:
    """The dropped ``OpenClaudeError`` base no longer exists on the module."""
    assert not hasattr(exceptions, "OpenClaudeError")


def test_unavailable_error_narrow_construction() -> None:
    """The spec's narrow ``(message, grpc_url)`` form works with retriable defaulting True."""
    err = OpenClaudeUnavailableError("backend unreachable", "localhost:50051")
    assert str(err) == "backend unreachable"
    assert err.grpc_url == "localhost:50051"
    assert err.retriable is True
    assert err.status_code is None


def test_unavailable_error_superset_kwargs_client_contract() -> None:
    """The client.py contract: keyword-only ``retriable``/``status_code`` are stored."""
    err = OpenClaudeUnavailableError(
        "OpenClaude gRPC stream failed at the transport level",
        retriable=False,
        status_code="PERMISSION_DENIED",
    )
    assert err.grpc_url is None
    assert err.retriable is False
    assert err.status_code == "PERMISSION_DENIED"


def test_unavailable_error_defaults() -> None:
    """Constructed with only a message, grpc_url is None and retriable defaults True."""
    err = OpenClaudeUnavailableError("unreachable")
    assert err.grpc_url is None
    assert err.retriable is True
    assert err.status_code is None


def test_permission_denied_error_shape() -> None:
    """PermissionDeniedError stores tool/binary, is non-retriable, formats a fixed message."""
    err = PermissionDeniedError(tool="Bash", denied_binary="rm")
    assert err.tool == "Bash"
    assert err.denied_binary == "rm"
    assert err.retriable is False
    assert PermissionDeniedError.retriable is False
    assert str(err) == ("OpenClaude requested non-allowlisted command 'rm' via tool 'Bash'; denied (non-retriable).")


def test_config_error_message_and_fields() -> None:
    """OpenClaudeConfigError stores field/reason and formats the canonical message."""
    err = OpenClaudeConfigError(field="grpc_url", reason="must be bare host[:port]")
    assert err.field == "grpc_url"
    assert err.reason == "must be bare host[:port]"
    assert str(err) == "OpenClaudeSettings.grpc_url: must be bare host[:port]"
    assert isinstance(err, ValueError)


def test_config_error_is_catchable_as_valueerror() -> None:
    """OpenClaudeConfigError is caught by ``except ValueError`` (Pydantic contract)."""
    with pytest.raises(ValueError):
        raise OpenClaudeConfigError(field="f", reason="r")


def test_config_reexport_identity() -> None:
    """``config.OpenClaudeConfigError`` is the same object as the canonical class."""
    assert openclaude_config.OpenClaudeConfigError is OpenClaudeConfigError


def test_config_error_distinct_from_router_config_validation_error() -> None:
    """OpenClaudeConfigError and router ConfigValidationError never subclass each other."""
    assert not issubclass(OpenClaudeConfigError, ConfigValidationError)
    assert not issubclass(ConfigValidationError, OpenClaudeConfigError)
    assert OpenClaudeConfigError is not ConfigValidationError


def test_no_payload_leakage_by_construction() -> None:
    """Only caller-provided fields reach a message; no extra payload is embedded."""
    payload = "SECRET_TOKEN=abcd1234 in dump 0xdeadbeef"

    unavailable = OpenClaudeUnavailableError("transport failure", status_code="UNAVAILABLE")
    assert payload not in str(unavailable)

    # A caller who names a binary sees only that binary, not a full command line.
    permission = PermissionDeniedError(tool="Bash", denied_binary="curl")
    assert payload not in str(permission)

    # If a caller *does* pass payload as the reason, it appears verbatim and only
    # there - the type adds nothing beyond the caller-provided field/reason.
    config_err = OpenClaudeConfigError(field="grpc_url", reason=payload)
    assert str(config_err) == f"OpenClaudeSettings.grpc_url: {payload}"


def test_import_pulls_in_no_grpc() -> None:
    """Importing the leaf exceptions module never imports ``grpc`` (C3)."""
    grpc_before = "grpc" in sys.modules
    importlib_reimport = __import__("aegis_swr.openclaude.exceptions", fromlist=["*"])
    assert importlib_reimport is exceptions
    # Import must not have introduced grpc if it was absent.
    if not grpc_before:
        assert "grpc" not in sys.modules
