"""Unit tests for :mod:`aegis_swr.openclaude.config`."""

from __future__ import annotations

import os

import pytest
from loguru import logger

from aegis_swr.openclaude.config import OpenClaudeConfigError, OpenClaudeSettings


@pytest.fixture(autouse=True)
def _clear_openclaude_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no ambient ``OPENCLAUDE_*`` env var leaks into the defaults tests."""
    for key in list(os.environ):
        if key.startswith("OPENCLAUDE_"):
            monkeypatch.delenv(key, raising=False)


def _capture_logs() -> tuple[list[str], int]:
    """Attach a loguru sink capturing rendered messages; return (records, sink_id)."""
    records: list[str] = []
    sink_id = logger.add(records.append, level="WARNING", format="{message}")
    return records, sink_id


def test_defaults_no_env() -> None:
    """[Unit] openclaude config: defaults construct cleanly with grpc_url unset.

    Scenario: settings are built with no ``OPENCLAUDE_*`` env vars set.

    Boundaries: exercises the documented default values only.

    On failure, first check: ``grpc_url`` must be ``None`` and every documented default
    (tools, allowlist, timeouts, binary, TLS) must match.
    """
    settings = OpenClaudeSettings()
    assert settings.grpc_url is None
    assert settings.allowed_tools == ["Read", "Grep", "Glob", "Bash"]
    assert settings.bash_allowlist == ["gtags", "global", "semgrep", "rg", "find", "cat"]
    assert settings.max_response_tokens == 4096
    assert settings.connect_timeout_s == 10
    assert settings.request_timeout_s == 120
    assert settings.auto_start is False
    assert settings.process_binary == "openclaude"
    assert settings.use_tls is False


def test_grpc_url_https_rejected() -> None:
    """[Unit] openclaude config: a scheme-prefixed grpc_url is rejected.

    Scenario: ``grpc_url`` is set to an ``https://`` URL.

    Boundaries: exercises the grpc_url host[:port] validator only.

    On failure, first check: construction must raise ``OpenClaudeConfigError`` on the
    ``grpc_url`` field.
    """
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(grpc_url="https://bad")
    assert exc.value.field == "grpc_url"


def test_grpc_url_http_rejected() -> None:
    """[Unit] openclaude config: an http scheme grpc_url is also rejected.

    Scenario: ``grpc_url`` is set to an ``http://`` URL.

    Boundaries: exercises the grpc_url host[:port] validator only.

    On failure, first check: construction must raise ``OpenClaudeConfigError``.
    """
    with pytest.raises(OpenClaudeConfigError):
        OpenClaudeSettings(grpc_url="http://bad")


def test_grpc_url_host_port_ok() -> None:
    """[Unit] openclaude config: a bare host:port grpc_url is accepted.

    Scenario: ``grpc_url`` is set to ``localhost:50051``.

    Boundaries: exercises the grpc_url validator's accept path.

    On failure, first check: the value must be stored verbatim.
    """
    settings = OpenClaudeSettings(grpc_url="localhost:50051")
    assert settings.grpc_url == "localhost:50051"


def test_grpc_url_empty_string_is_unset() -> None:
    """[Unit] openclaude config: an empty/whitespace grpc_url coerces to None.

    Scenario: ``grpc_url`` is set to an empty and a whitespace-only string.

    Boundaries: models an unset CI secret expanding to ``""`` - it must mean "not
    configured", never a validation error.

    On failure, first check: both values must coerce ``grpc_url`` to ``None``.
    """
    assert OpenClaudeSettings(grpc_url="").grpc_url is None
    assert OpenClaudeSettings(grpc_url="   ").grpc_url is None


def test_grpc_url_empty_env_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: an empty grpc_url env var coerces to None.

    Scenario: ``OPENCLAUDE_GRPC_URL`` is set to an empty string.

    Boundaries: models the unset-CI-secret case flowing through the env.

    On failure, first check: ``grpc_url`` must be ``None``, not a validation error.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "")
    assert OpenClaudeSettings().grpc_url is None


def test_grpc_url_invalid_chars_rejected() -> None:
    """[Unit] openclaude config: a grpc_url host with illegal characters is rejected.

    Scenario: ``grpc_url`` contains an embedded space.

    Boundaries: exercises the grpc_url validator's character set.

    On failure, first check: construction must raise ``OpenClaudeConfigError``.
    """
    with pytest.raises(OpenClaudeConfigError):
        OpenClaudeSettings(grpc_url="local host:50051")


def test_grpc_url_trailing_newline_rejected() -> None:
    """[Unit] openclaude config: a trailing newline in grpc_url is rejected.

    Scenario: ``grpc_url`` ends with a newline character.

    Boundaries: regression guard for the anchored host[:port] pattern.

    On failure, first check: construction must raise ``OpenClaudeConfigError`` on the
    ``grpc_url`` field.
    """
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(grpc_url="localhost:50051\n")
    assert exc.value.field == "grpc_url"


def test_unknown_tool_rejected() -> None:
    """[Unit] openclaude config: an unrecognised allowed-tool name is rejected.

    Scenario: ``allowed_tools`` includes ``WriteFile``.

    Boundaries: exercises the allowed-tools validator.

    On failure, first check: construction must raise ``OpenClaudeConfigError`` on the
    ``allowed_tools`` field.
    """
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(allowed_tools=["Read", "WriteFile"])
    assert exc.value.field == "allowed_tools"


def test_write_tool_warns_not_raises() -> None:
    """[Unit] openclaude config: allowing Write warns but does not raise.

    Scenario: ``allowed_tools`` includes ``Write`` while a WARNING sink is attached.

    Boundaries: exercises the soft-warning branch of the tools validator.

    On failure, first check: the value must be kept and a compromised-read-only-mode
    warning must be emitted.
    """
    records, sink_id = _capture_logs()
    try:
        settings = OpenClaudeSettings(allowed_tools=["Read", "Write"])
    finally:
        logger.remove(sink_id)
    assert settings.allowed_tools == ["Read", "Write"]
    combined = "\n".join(records)
    assert "Write" in combined
    assert "read-only forensic mode is compromised" in combined


def test_bash_allowlist_dangerous_binary_warns_not_raises() -> None:
    """[Unit] openclaude config: a dangerous bash binary warns but is not rejected.

    Scenario: ``bash_allowlist`` includes ``sh`` while a WARNING sink is attached.

    Boundaries: exercises the soft-warning branch of the allowlist validator.

    On failure, first check: the value must be kept and a ``dangerous`` warning emitted.
    """
    records, sink_id = _capture_logs()
    try:
        settings = OpenClaudeSettings(bash_allowlist=["rg", "sh"])
    finally:
        logger.remove(sink_id)
    assert settings.bash_allowlist == ["rg", "sh"]
    combined = "\n".join(records)
    assert "sh" in combined
    assert "dangerous" in combined


def test_bash_allowlist_defaults_do_not_warn() -> None:
    """[Unit] openclaude config: the default allowlist emits no warning.

    Scenario: default settings are built while a WARNING sink is attached.

    Boundaries: proves the spec-defined defaults are all benign.

    On failure, first check: the default allowlist must match and no records be captured.
    """
    records, sink_id = _capture_logs()
    try:
        settings = OpenClaudeSettings()
    finally:
        logger.remove(sink_id)
    assert settings.bash_allowlist == ["gtags", "global", "semgrep", "rg", "find", "cat"]
    assert records == []


def test_max_tokens_too_low_rejected() -> None:
    """[Unit] openclaude config: a below-floor max_response_tokens is rejected.

    Scenario: ``max_response_tokens`` is set to 100.

    Boundaries: exercises the token-range validator's lower bound.

    On failure, first check: construction must raise ``OpenClaudeConfigError`` on the
    ``max_response_tokens`` field.
    """
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(max_response_tokens=100)
    assert exc.value.field == "max_response_tokens"


def test_max_tokens_too_high_rejected() -> None:
    """[Unit] openclaude config: an above-ceiling max_response_tokens is rejected.

    Scenario: ``max_response_tokens`` is set to 65537.

    Boundaries: exercises the token-range validator's upper bound.

    On failure, first check: construction must raise ``OpenClaudeConfigError``.
    """
    with pytest.raises(OpenClaudeConfigError):
        OpenClaudeSettings(max_response_tokens=65537)


def test_request_timeout_not_greater_than_connect_rejected() -> None:
    """[Unit] openclaude config: request_timeout must exceed connect_timeout.

    Scenario: connect timeout 100 with request timeout 10.

    Boundaries: exercises the cross-field timeout validator.

    On failure, first check: construction must raise ``OpenClaudeConfigError`` on the
    ``request_timeout_s`` field.
    """
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(connect_timeout_s=100, request_timeout_s=10)
    assert exc.value.field == "request_timeout_s"


def test_request_timeout_equal_to_connect_rejected() -> None:
    """[Unit] openclaude config: equal timeouts fail the strictly-greater check.

    Scenario: connect and request timeouts both 30.

    Boundaries: exercises the cross-field timeout validator's boundary.

    On failure, first check: construction must raise ``OpenClaudeConfigError`` on the
    ``request_timeout_s`` field.
    """
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(connect_timeout_s=30, request_timeout_s=30)
    assert exc.value.field == "request_timeout_s"


def test_connect_timeout_non_positive_rejected() -> None:
    """[Unit] openclaude config: a non-positive connect_timeout is rejected.

    Scenario: ``connect_timeout_s`` is set to 0.

    Boundaries: exercises the connect-timeout validator.

    On failure, first check: construction must raise ``OpenClaudeConfigError`` on the
    ``connect_timeout_s`` field.
    """
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(connect_timeout_s=0)
    assert exc.value.field == "connect_timeout_s"


def test_allowed_tools_csv_env_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: a CSV allowed-tools env parses into a list.

    Scenario: ``OPENCLAUDE_ALLOWED_TOOLS`` is a comma-separated string with spaces.

    Boundaries: exercises the CSV env source splitting.

    On failure, first check: the parsed list must be the trimmed token sequence.
    """
    monkeypatch.setenv("OPENCLAUDE_ALLOWED_TOOLS", "Read, Grep ,Glob,Bash")
    settings = OpenClaudeSettings()
    assert settings.allowed_tools == ["Read", "Grep", "Glob", "Bash"]


def test_bash_allowlist_csv_env_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: a CSV bash-allowlist env parses into a list.

    Scenario: ``OPENCLAUDE_BASH_ALLOWLIST`` is a comma-separated string with a trailing
    empty token.

    Boundaries: exercises the CSV env source splitting and empty-token pruning.

    On failure, first check: the parsed list must be the trimmed, non-empty tokens.
    """
    monkeypatch.setenv("OPENCLAUDE_BASH_ALLOWLIST", "rg,find, cat ,")
    settings = OpenClaudeSettings()
    assert settings.bash_allowlist == ["rg", "find", "cat"]


def test_use_tls_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: OPENCLAUDE_USE_TLS toggles the use_tls field.

    Scenario: ``OPENCLAUDE_USE_TLS`` is set to ``true``.

    Boundaries: exercises boolean env parsing.

    On failure, first check: ``use_tls`` must be ``True``.
    """
    monkeypatch.setenv("OPENCLAUDE_USE_TLS", "true")
    settings = OpenClaudeSettings()
    assert settings.use_tls is True


def test_max_tokens_reads_documented_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: OPENCLAUDE_MAX_TOKENS populates max_response_tokens.

    Scenario: ``OPENCLAUDE_MAX_TOKENS`` is set to 1024.

    Boundaries: exercises the documented env alias.

    On failure, first check: ``max_response_tokens`` must be 1024.
    """
    monkeypatch.setenv("OPENCLAUDE_MAX_TOKENS", "1024")
    settings = OpenClaudeSettings()
    assert settings.max_response_tokens == 1024


def test_connect_timeout_reads_documented_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: OPENCLAUDE_CONNECT_TIMEOUT populates connect_timeout_s.

    Scenario: ``OPENCLAUDE_CONNECT_TIMEOUT`` is set to 5.

    Boundaries: exercises the documented env alias.

    On failure, first check: ``connect_timeout_s`` must be 5.
    """
    monkeypatch.setenv("OPENCLAUDE_CONNECT_TIMEOUT", "5")
    settings = OpenClaudeSettings()
    assert settings.connect_timeout_s == 5


def test_request_timeout_reads_documented_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: OPENCLAUDE_REQUEST_TIMEOUT populates request_timeout_s.

    Scenario: ``OPENCLAUDE_REQUEST_TIMEOUT`` is set to 90.

    Boundaries: exercises the documented env alias.

    On failure, first check: ``request_timeout_s`` must be 90.
    """
    monkeypatch.setenv("OPENCLAUDE_REQUEST_TIMEOUT", "90")
    settings = OpenClaudeSettings()
    assert settings.request_timeout_s == 90


def test_process_binary_reads_documented_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: OPENCLAUDE_BINARY populates process_binary.

    Scenario: ``OPENCLAUDE_BINARY`` is set to ``/opt/oc``.

    Boundaries: exercises the documented env alias.

    On failure, first check: ``process_binary`` must be ``/opt/oc``.
    """
    monkeypatch.setenv("OPENCLAUDE_BINARY", "/opt/oc")
    settings = OpenClaudeSettings()
    assert settings.process_binary == "/opt/oc"


# --- Postinstall best-effort contract ---------------------------------------


def test_postinstall_swallows_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: the postinstall hook swallows a subprocess OSError.

    Scenario: ``subprocess.run`` is patched to raise ``OSError`` after the ``which``
    check passes.

    Boundaries: exercises the best-effort contract of ``install_openclaude_cli``.

    On failure, first check: the call must complete without raising.
    """
    import scripts.postinstall_openclaude as postinstall

    monkeypatch.setattr(postinstall.shutil, "which", lambda _cmd: "/usr/bin/npm")

    def _raise_oserror(*_args: object, **_kwargs: object) -> None:
        """Raise ``OSError`` to simulate npm vanishing after the ``which`` check."""
        raise OSError("npm vanished after the which() check")

    monkeypatch.setattr(postinstall.subprocess, "run", _raise_oserror)
    postinstall.install_openclaude_cli()


# --- Composition into the top-level Settings object -------------------------


def test_settings_composition_defaults_no_env() -> None:
    """[Unit] openclaude config: top-level Settings exposes OpenClaudeSettings.

    Scenario: a top-level ``Settings`` is built with no env vars.

    Boundaries: exercises settings composition wiring.

    On failure, first check: ``settings.openclaude`` must be an ``OpenClaudeSettings``
    with ``grpc_url`` ``None``.
    """
    from aegis_swr.config.settings import Settings

    settings = Settings()
    assert isinstance(settings.openclaude, OpenClaudeSettings)
    assert settings.openclaude.grpc_url is None


def test_settings_composition_reads_flat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] openclaude config: a flat grpc_url env flows through composition.

    Scenario: ``OPENCLAUDE_GRPC_URL`` is set and a top-level ``Settings`` is built.

    Boundaries: exercises env-through-composition wiring.

    On failure, first check: ``settings.openclaude.grpc_url`` must equal the env value.
    """
    from aegis_swr.config.settings import Settings

    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")
    settings = Settings()
    assert settings.openclaude.grpc_url == "localhost:50051"


def test_settings_composition_leaves_siblings_intact() -> None:
    """[Unit] openclaude config: adding openclaude leaves sibling sections intact.

    Scenario: a top-level ``Settings`` is built and its other sections inspected.

    Boundaries: regression guard for settings composition.

    On failure, first check: ``core`` must remain a ``CoreSettings`` and the AI backend
    settings must still be present.
    """
    from aegis_swr.config.settings import CoreSettings, Settings

    settings = Settings()
    assert isinstance(settings.core, CoreSettings)
    assert settings.backends.ai is not None
