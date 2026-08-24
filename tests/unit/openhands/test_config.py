"""Unit tests for :mod:`aegis_swr.openhands.config`."""

from __future__ import annotations

import os

import pytest
from loguru import logger

from aegis_swr.openhands.config import OpenHandsConfigError, OpenHandsSettings


@pytest.fixture(autouse=True)
def _clear_openhands_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure no ambient ``OPENHANDS_*`` env var leaks into the defaults tests."""
    for key in list(os.environ):
        if key.startswith("OPENHANDS_"):
            monkeypatch.delenv(key, raising=False)


def _capture_logs() -> tuple[list[str], int]:
    """Attach a loguru sink capturing rendered messages; return (records, sink_id)."""
    records: list[str] = []
    sink_id = logger.add(records.append, level="WARNING", format="{message}")
    return records, sink_id


# --- Subtask 01: fields, defaults, URL, CSV parsing -------------------------


def test_defaults_no_env():
    """[Unit] openhands config: defaults construct cleanly with server_url unset.

    Scenario: settings are built with no ``OPENHANDS_*`` env vars set.

    Boundaries: exercises the documented default values only.

    On failure, first check: ``server_url`` must be ``None`` and every documented
    default (runtime, tools, timeouts, flags) must match.
    """
    settings = OpenHandsSettings()
    assert settings.server_url is None
    assert settings.runtime_mode == "docker"
    assert settings.allowed_tools == ["read", "grep", "glob", "browse"]
    assert settings.connect_timeout_s == 10
    assert settings.request_timeout_s == 120
    assert settings.auto_start is False
    assert settings.allow_unsandboxed_runtime is False


def test_server_url_empty_string_is_unset():
    """[Unit] openhands config: an empty/whitespace server_url coerces to None.

    Scenario: ``server_url`` is set to an empty and a whitespace-only string.

    Boundaries: models an unset CI secret expanding to ``""`` - it must mean "not
    configured", never a validation error.

    On failure, first check: both values must coerce ``server_url`` to ``None``.
    """
    assert OpenHandsSettings(server_url="").server_url is None
    assert OpenHandsSettings(server_url="   ").server_url is None


def test_server_url_empty_env_is_unset(monkeypatch: pytest.MonkeyPatch):
    """[Unit] openhands config: an empty server_url env var coerces to None.

    Scenario: ``OPENHANDS_SERVER_URL`` is set to an empty string.

    Boundaries: models the unset-CI-secret case flowing through the env.

    On failure, first check: ``server_url`` must be ``None``, not a validation error.
    """
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "")
    assert OpenHandsSettings().server_url is None


def test_server_url_http_accepted():
    """[Unit] openhands config: a well-formed http server_url is preserved.

    Scenario: ``server_url`` is set to ``http://localhost:3000``.

    Boundaries: exercises the server_url validator's accept path.

    On failure, first check: the value must be stored verbatim.
    """
    settings = OpenHandsSettings(server_url="http://localhost:3000")
    assert settings.server_url == "http://localhost:3000"


def test_server_url_https_accepted():
    """[Unit] openhands config: a well-formed https server_url is preserved.

    Scenario: ``server_url`` is set to ``https://oh.example.com:8443``.

    Boundaries: exercises the server_url validator's https accept path.

    On failure, first check: the value must be stored verbatim.
    """
    settings = OpenHandsSettings(server_url="https://oh.example.com:8443")
    assert settings.server_url == "https://oh.example.com:8443"


def test_server_url_missing_scheme_rejected():
    """[Unit] openhands config: a scheme-less server_url is rejected.

    Scenario: ``server_url`` is a bare host[:port] (the OpenClaude shape).

    Boundaries: exercises the inverse-of-OpenClaude scheme requirement.

    On failure, first check: construction must raise ``OpenHandsConfigError`` on the
    ``server_url`` field, and the message must not echo the value.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(server_url="localhost:3000")
    assert exc.value.field == "server_url"
    assert "localhost" not in str(exc.value)


def test_server_url_not_a_url_rejected():
    """[Unit] openhands config: a malformed server_url is rejected without echo.

    Scenario: ``server_url`` is set to ``not-a-url``.

    Boundaries: exercises the server_url validator's reject path and C13 no-echo.

    On failure, first check: construction must raise ``OpenHandsConfigError`` whose
    message does not contain the offending value.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(server_url="not-a-url")
    assert exc.value.field == "server_url"
    assert "not-a-url" not in str(exc.value)


def test_server_url_wrong_scheme_rejected():
    """[Unit] openhands config: a non-http(s) scheme server_url is rejected.

    Scenario: ``server_url`` uses a ``ws://`` scheme (the client upgrades itself).

    Boundaries: exercises the http(s)-only requirement.

    On failure, first check: construction must raise ``OpenHandsConfigError`` on the
    ``server_url`` field.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(server_url="ws://localhost:3000")
    assert exc.value.field == "server_url"


def test_unknown_runtime_rejected():
    """[Unit] openhands config: an unrecognised runtime name is rejected.

    Scenario: ``runtime_mode`` is set to ``podman``.

    Boundaries: exercises the runtime-membership validator.

    On failure, first check: construction must raise ``OpenHandsConfigError`` on the
    ``runtime_mode`` field.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(runtime_mode="podman")
    assert exc.value.field == "runtime_mode"


def test_unknown_tool_rejected():
    """[Unit] openhands config: an unrecognised allowed-tool name is rejected.

    Scenario: ``allowed_tools`` includes ``teleport``.

    Boundaries: exercises the allowed-tools validator.

    On failure, first check: construction must raise ``OpenHandsConfigError`` on the
    ``allowed_tools`` field.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(allowed_tools=["read", "teleport"])
    assert exc.value.field == "allowed_tools"


def test_write_tool_warns_not_raises():
    """[Unit] openhands config: allowing write warns but does not raise.

    Scenario: ``allowed_tools`` includes ``write`` while a WARNING sink is attached.

    Boundaries: exercises the soft-warning branch of the tools validator.

    On failure, first check: the value must be kept and a compromised-read-only-mode
    warning naming ``write`` must be emitted exactly once.
    """
    records, sink_id = _capture_logs()
    try:
        settings = OpenHandsSettings(allowed_tools=["read", "write"])
    finally:
        logger.remove(sink_id)
    assert settings.allowed_tools == ["read", "write"]
    combined = "\n".join(records)
    assert "write" in combined
    assert "read-only forensic mode is compromised" in combined
    assert len(records) == 1


def test_connect_timeout_non_positive_rejected():
    """[Unit] openhands config: a non-positive connect_timeout is rejected.

    Scenario: ``connect_timeout_s`` is set to 0.

    Boundaries: exercises the connect-timeout validator.

    On failure, first check: construction must raise ``OpenHandsConfigError`` on the
    ``connect_timeout_s`` field.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(connect_timeout_s=0)
    assert exc.value.field == "connect_timeout_s"


def test_request_timeout_not_greater_than_connect_rejected():
    """[Unit] openhands config: request_timeout must exceed connect_timeout.

    Scenario: connect timeout 100 with request timeout 10.

    Boundaries: exercises the cross-field timeout validator.

    On failure, first check: construction must raise ``OpenHandsConfigError`` on the
    ``request_timeout_s`` field.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(connect_timeout_s=100, request_timeout_s=10)
    assert exc.value.field == "request_timeout_s"


def test_request_timeout_equal_to_connect_rejected():
    """[Unit] openhands config: equal timeouts fail the strictly-greater check.

    Scenario: connect and request timeouts both 30.

    Boundaries: exercises the cross-field timeout validator's boundary.

    On failure, first check: construction must raise ``OpenHandsConfigError`` on the
    ``request_timeout_s`` field.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(connect_timeout_s=30, request_timeout_s=30)
    assert exc.value.field == "request_timeout_s"


def test_allowed_tools_csv_env_roundtrip(monkeypatch: pytest.MonkeyPatch):
    """[Unit] openhands config: a CSV allowed-tools env parses into a list.

    Scenario: ``OPENHANDS_ALLOWED_TOOLS`` is a comma-separated string with spaces.

    Boundaries: exercises the CSV env source splitting.

    On failure, first check: the parsed list must be the trimmed token sequence.
    """
    monkeypatch.setenv("OPENHANDS_ALLOWED_TOOLS", "read, grep ,glob")
    settings = OpenHandsSettings()
    assert settings.allowed_tools == ["read", "grep", "glob"]


def test_allowed_tools_csv_direct_string():
    """[Unit] openhands config: a comma-separated string passed in code is coerced.

    Scenario: ``allowed_tools`` is passed as a raw CSV string to the constructor.

    Boundaries: exercises the ``mode="before"`` coercion validator.

    On failure, first check: the string must split into the trimmed token list.
    """
    settings = OpenHandsSettings(allowed_tools="read,grep")
    assert settings.allowed_tools == ["read", "grep"]


def test_timeouts_read_documented_env(monkeypatch: pytest.MonkeyPatch):
    """[Unit] openhands config: the documented timeout env aliases populate fields.

    Scenario: ``OPENHANDS_CONNECT_TIMEOUT`` and ``OPENHANDS_REQUEST_TIMEOUT`` are set.

    Boundaries: exercises the documented env aliases.

    On failure, first check: both timeout fields must reflect the env values.
    """
    monkeypatch.setenv("OPENHANDS_CONNECT_TIMEOUT", "5")
    monkeypatch.setenv("OPENHANDS_REQUEST_TIMEOUT", "90")
    settings = OpenHandsSettings()
    assert settings.connect_timeout_s == 5
    assert settings.request_timeout_s == 90


def test_auto_start_empty_env_falls_back_to_false(monkeypatch: pytest.MonkeyPatch):
    """[Unit] openhands config: an empty OPENHANDS_AUTO_START falls back to False.

    Scenario: ``OPENHANDS_AUTO_START`` is set to an empty string (an unset CI secret
    expanding to ``""``).

    Boundaries: regression guard for FIX 2 - an empty bool value must never raise a
    raw pydantic ``bool_parsing`` error.

    On failure, first check: the ``_coerce_bool_flags`` mode="before" validator must
    coerce the blank value to ``False``.
    """
    monkeypatch.setenv("OPENHANDS_AUTO_START", "")
    assert OpenHandsSettings().auto_start is False


def test_allow_unsandboxed_empty_env_falls_back_to_false(monkeypatch: pytest.MonkeyPatch):
    """[Unit] openhands config: an empty OPENHANDS_ALLOW_UNSANDBOXED stays False.

    Scenario: ``OPENHANDS_ALLOW_UNSANDBOXED`` is set to an empty string.

    Boundaries: regression guard for FIX 2 - the fail-safe direction, a blank value
    must never flip the sandbox override permissive.

    On failure, first check: ``_coerce_bool_flags`` must coerce the blank value to
    ``False`` so the Docker sandbox stays enforced.
    """
    monkeypatch.setenv("OPENHANDS_ALLOW_UNSANDBOXED", "")
    assert OpenHandsSettings().allow_unsandboxed_runtime is False


def test_bool_flags_blank_string_fall_back_to_false():
    """[Unit] openhands config: whitespace-only bool flags fall back to False.

    Scenario: both bool flags are passed as whitespace-only strings to the constructor.

    Boundaries: regression guard for FIX 2 exercising the coercion validator directly.

    On failure, first check: ``_coerce_bool_flags`` must return ``False`` for a blank
    string on both fields.
    """
    settings = OpenHandsSettings(auto_start="   ", allow_unsandboxed_runtime="  ")
    assert settings.auto_start is False
    assert settings.allow_unsandboxed_runtime is False


def test_auto_start_reads_env(monkeypatch: pytest.MonkeyPatch):
    """[Unit] openhands config: OPENHANDS_AUTO_START toggles the auto_start field.

    Scenario: ``OPENHANDS_AUTO_START`` is set to ``true``.

    Boundaries: exercises boolean env parsing.

    On failure, first check: ``auto_start`` must be ``True``.
    """
    monkeypatch.setenv("OPENHANDS_AUTO_START", "true")
    settings = OpenHandsSettings()
    assert settings.auto_start is True


# --- Subtask 02: sandbox-runtime enforcement --------------------------------


def test_default_runtime_docker_no_warning():
    """[Unit] openhands config: the default docker runtime emits no sandbox warning.

    Scenario: default settings are built while a WARNING sink is attached.

    Boundaries: proves the sandboxed default path adds zero friction.

    On failure, first check: construction must succeed and capture no records.
    """
    records, sink_id = _capture_logs()
    try:
        settings = OpenHandsSettings()
    finally:
        logger.remove(sink_id)
    assert settings.runtime_mode == "docker"
    assert records == []


def test_remote_runtime_sandboxed_no_warning():
    """[Unit] openhands config: the remote runtime is sandboxed and emits no warning.

    Scenario: ``runtime_mode`` is set to ``remote`` with a WARNING sink attached.

    Boundaries: exercises the second sandboxed runtime's no-friction path.

    On failure, first check: construction must succeed and capture no records.
    """
    records, sink_id = _capture_logs()
    try:
        settings = OpenHandsSettings(runtime_mode="remote")
    finally:
        logger.remove(sink_id)
    assert settings.runtime_mode == "remote"
    assert records == []


def test_local_runtime_without_override_rejected():
    """[Unit] openhands config: a local runtime without the override is rejected.

    Scenario: ``runtime_mode`` is ``local`` and ``allow_unsandboxed_runtime`` is default.

    Boundaries: exercises the sandbox-enforcement model-validator's reject path.

    On failure, first check: construction must raise ``OpenHandsConfigError`` on the
    ``runtime_mode`` field, name ``OPENHANDS_ALLOW_UNSANDBOXED`` and the ADR
    requirement, and contain no server_url/payload text.
    """
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings(runtime_mode="local")
    assert exc.value.field == "runtime_mode"
    message = str(exc.value)
    assert "OPENHANDS_ALLOW_UNSANDBOXED" in message
    assert "ADR" in message


def test_local_runtime_with_override_permitted_with_warning():
    """[Unit] openhands config: a local runtime with the override warns, not raises.

    Scenario: ``runtime_mode`` is ``local`` with ``allow_unsandboxed_runtime=True``
    while a WARNING sink is attached.

    Boundaries: exercises the permit-but-warn-loudly branch of the enforcement validator.

    On failure, first check: construction must succeed and emit a single warning that
    the Docker sandbox is disabled and an ADR is required.
    """
    records, sink_id = _capture_logs()
    try:
        settings = OpenHandsSettings(runtime_mode="local", allow_unsandboxed_runtime=True)
    finally:
        logger.remove(sink_id)
    assert settings.runtime_mode == "local"
    assert len(records) == 1
    combined = records[0]
    assert "DISABLED" in combined
    assert "ADR" in combined


def test_local_runtime_env_without_override_rejected(monkeypatch: pytest.MonkeyPatch):
    """[Unit] openhands config: OPENHANDS_RUNTIME=local alone is rejected.

    Scenario: ``OPENHANDS_RUNTIME`` is ``local`` with no override env var set.

    Boundaries: exercises the enforcement validator via the environment path.

    On failure, first check: construction must raise ``OpenHandsConfigError``.
    """
    monkeypatch.setenv("OPENHANDS_RUNTIME", "local")
    with pytest.raises(OpenHandsConfigError) as exc:
        OpenHandsSettings()
    assert exc.value.field == "runtime_mode"


def test_local_runtime_env_with_override_permitted(monkeypatch: pytest.MonkeyPatch):
    """[Unit] openhands config: OPENHANDS_ALLOW_UNSANDBOXED permits a local runtime.

    Scenario: ``OPENHANDS_RUNTIME=local`` and ``OPENHANDS_ALLOW_UNSANDBOXED=true``.

    Boundaries: exercises the override via the environment path.

    On failure, first check: construction must succeed with a single warning.
    """
    monkeypatch.setenv("OPENHANDS_RUNTIME", "local")
    monkeypatch.setenv("OPENHANDS_ALLOW_UNSANDBOXED", "true")
    records, sink_id = _capture_logs()
    try:
        settings = OpenHandsSettings()
    finally:
        logger.remove(sink_id)
    assert settings.runtime_mode == "local"
    assert settings.allow_unsandboxed_runtime is True
    assert len(records) == 1


def test_override_inert_when_runtime_sandboxed():
    """[Unit] openhands config: the override is inert for an already-sandboxed runtime.

    Scenario: ``runtime_mode='docker'`` with ``allow_unsandboxed_runtime=True`` while a
    WARNING sink is attached.

    Boundaries: exercises the sandboxed-runtime short-circuit of the enforcement validator.

    On failure, first check: construction must succeed and emit no warning.
    """
    records, sink_id = _capture_logs()
    try:
        settings = OpenHandsSettings(runtime_mode="docker", allow_unsandboxed_runtime=True)
    finally:
        logger.remove(sink_id)
    assert settings.runtime_mode == "docker"
    assert records == []
