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
    """No env vars set: constructs cleanly with documented defaults, grpc_url=None."""
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
    """A scheme-prefixed URL is rejected."""
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(grpc_url="https://bad")
    assert exc.value.field == "grpc_url"


def test_grpc_url_http_rejected() -> None:
    """An http:// scheme is also rejected."""
    with pytest.raises(OpenClaudeConfigError):
        OpenClaudeSettings(grpc_url="http://bad")


def test_grpc_url_host_port_ok() -> None:
    """A bare host:port value is accepted."""
    settings = OpenClaudeSettings(grpc_url="localhost:50051")
    assert settings.grpc_url == "localhost:50051"


def test_grpc_url_empty_string_is_unset() -> None:
    """An empty / whitespace grpc_url coerces to None, not a validation error.

    An unset CI secret expands to ``""`` (``OPENCLAUDE_GRPC_URL: ${{ secrets.X }}``);
    that must mean "not configured", never crash settings construction.
    """
    assert OpenClaudeSettings(grpc_url="").grpc_url is None
    assert OpenClaudeSettings(grpc_url="   ").grpc_url is None


def test_grpc_url_empty_env_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty ``OPENCLAUDE_GRPC_URL`` env var coerces to None (CI-secret case)."""
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "")
    assert OpenClaudeSettings().grpc_url is None


def test_grpc_url_invalid_chars_rejected() -> None:
    """A host containing illegal characters is rejected."""
    with pytest.raises(OpenClaudeConfigError):
        OpenClaudeSettings(grpc_url="local host:50051")


def test_grpc_url_trailing_newline_rejected() -> None:
    """A trailing newline must not sneak past the anchored host[:port] pattern."""
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(grpc_url="localhost:50051\n")
    assert exc.value.field == "grpc_url"


def test_unknown_tool_rejected() -> None:
    """An unrecognised tool name raises."""
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(allowed_tools=["Read", "WriteFile"])
    assert exc.value.field == "allowed_tools"


def test_write_tool_warns_not_raises() -> None:
    """Write is permitted but emits a warning about compromised read-only mode."""
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
    """A dangerous binary in bash_allowlist warns but is not rejected."""
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
    """The spec-defined default allowlist (incl. find/cat) emits no warning."""
    records, sink_id = _capture_logs()
    try:
        settings = OpenClaudeSettings()
    finally:
        logger.remove(sink_id)
    assert settings.bash_allowlist == ["gtags", "global", "semgrep", "rg", "find", "cat"]
    assert records == []


def test_max_tokens_too_low_rejected() -> None:
    """A max_response_tokens below the floor raises."""
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(max_response_tokens=100)
    assert exc.value.field == "max_response_tokens"


def test_max_tokens_too_high_rejected() -> None:
    """A max_response_tokens above the ceiling raises."""
    with pytest.raises(OpenClaudeConfigError):
        OpenClaudeSettings(max_response_tokens=65537)


def test_request_timeout_not_greater_than_connect_rejected() -> None:
    """request_timeout_s must exceed connect_timeout_s."""
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(connect_timeout_s=100, request_timeout_s=10)
    assert exc.value.field == "request_timeout_s"


def test_request_timeout_equal_to_connect_rejected() -> None:
    """request_timeout_s equal to connect_timeout_s fails the strictly-greater check."""
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(connect_timeout_s=30, request_timeout_s=30)
    assert exc.value.field == "request_timeout_s"


def test_connect_timeout_non_positive_rejected() -> None:
    """A non-positive connect_timeout_s raises."""
    with pytest.raises(OpenClaudeConfigError) as exc:
        OpenClaudeSettings(connect_timeout_s=0)
    assert exc.value.field == "connect_timeout_s"


def test_allowed_tools_csv_env_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """A comma-separated OPENCLAUDE_ALLOWED_TOOLS env value parses into a list."""
    monkeypatch.setenv("OPENCLAUDE_ALLOWED_TOOLS", "Read, Grep ,Glob,Bash")
    settings = OpenClaudeSettings()
    assert settings.allowed_tools == ["Read", "Grep", "Glob", "Bash"]


def test_bash_allowlist_csv_env_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """A comma-separated OPENCLAUDE_BASH_ALLOWLIST env value parses into a list."""
    monkeypatch.setenv("OPENCLAUDE_BASH_ALLOWLIST", "rg,find, cat ,")
    settings = OpenClaudeSettings()
    assert settings.bash_allowlist == ["rg", "find", "cat"]


def test_use_tls_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """OPENCLAUDE_USE_TLS toggles the use_tls field."""
    monkeypatch.setenv("OPENCLAUDE_USE_TLS", "true")
    settings = OpenClaudeSettings()
    assert settings.use_tls is True


def test_max_tokens_reads_documented_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented OPENCLAUDE_MAX_TOKENS env var populates max_response_tokens."""
    monkeypatch.setenv("OPENCLAUDE_MAX_TOKENS", "1024")
    settings = OpenClaudeSettings()
    assert settings.max_response_tokens == 1024


def test_connect_timeout_reads_documented_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented OPENCLAUDE_CONNECT_TIMEOUT env var populates connect_timeout_s."""
    monkeypatch.setenv("OPENCLAUDE_CONNECT_TIMEOUT", "5")
    settings = OpenClaudeSettings()
    assert settings.connect_timeout_s == 5


def test_request_timeout_reads_documented_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented OPENCLAUDE_REQUEST_TIMEOUT env var populates request_timeout_s."""
    monkeypatch.setenv("OPENCLAUDE_REQUEST_TIMEOUT", "90")
    settings = OpenClaudeSettings()
    assert settings.request_timeout_s == 90


def test_process_binary_reads_documented_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented OPENCLAUDE_BINARY env var populates process_binary."""
    monkeypatch.setenv("OPENCLAUDE_BINARY", "/opt/oc")
    settings = OpenClaudeSettings()
    assert settings.process_binary == "/opt/oc"


# --- Postinstall best-effort contract ---------------------------------------


def test_postinstall_swallows_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """install_openclaude_cli() must not raise when subprocess.run raises OSError."""
    import scripts.postinstall_openclaude as postinstall

    monkeypatch.setattr(postinstall.shutil, "which", lambda _cmd: "/usr/bin/npm")

    def _raise_oserror(*_args: object, **_kwargs: object) -> None:
        raise OSError("npm vanished after the which() check")

    monkeypatch.setattr(postinstall.subprocess, "run", _raise_oserror)
    postinstall.install_openclaude_cli()


# --- Composition into the top-level Settings object -------------------------


def test_settings_composition_defaults_no_env() -> None:
    """Top-level ``Settings`` exposes an ``OpenClaudeSettings`` with grpc_url=None."""
    from aegis_swr.config.settings import Settings

    settings = Settings()
    assert isinstance(settings.openclaude, OpenClaudeSettings)
    assert settings.openclaude.grpc_url is None


def test_settings_composition_reads_flat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flat ``OPENCLAUDE_GRPC_URL`` flows through composition into ``Settings``."""
    from aegis_swr.config.settings import Settings

    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")
    settings = Settings()
    assert settings.openclaude.grpc_url == "localhost:50051"


def test_settings_composition_leaves_siblings_intact() -> None:
    """Adding ``openclaude`` does not disturb existing sub-settings sections."""
    from aegis_swr.config.settings import CoreSettings, Settings

    settings = Settings()
    assert isinstance(settings.core, CoreSettings)
    assert settings.backends.ai is not None
