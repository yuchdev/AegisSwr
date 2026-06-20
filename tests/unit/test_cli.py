"""Unit tests for the CLI - all Orchestrator calls mocked"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
import typer.testing

from aegis_swr.cli._config import (
    load_analyze_config,
    save_analyze_config,
)
from aegis_swr.cli.commands import app
from aegis_swr.core.schemas import (
    ConfidenceLevel,
    HITLRequest,
    Hypothesis,
    IncidentMode,
    RCAReport,
)

runner = typer.testing.CliRunner()

_MOCK_RUN = "aegis_swr.core.orchestrator.Orchestrator.run"
_MOCK_STREAM_EVENTS = "aegis_swr.core.orchestrator.Orchestrator.stream_events"


def _report(with_hitl: bool = False) -> RCAReport:
    return RCAReport(
        mode=IncidentMode.LOG_FORENSICS,
        root_cause="UAF in serialize()",
        confidence_score=0.88,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(root_cause="UAF", confidence=0.88),
        consensus_rounds=1,
        hitl_request=HITLRequest(
            question="What DB pool size?",
            context_summary="deadlocked",
        )
        if with_hitl
        else None,
    )


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------


def test_python_m_entry_point_runs():
    """``python -m aegis_swr.cli`` launches the same Typer app as ``aegis``."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "aegis_swr.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "analyze" in result.stdout
    assert "Usage:" in result.stdout


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_analyze_help():
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--dump" in result.output
    assert "--config" in result.output
    assert "--save-config" in result.output
    assert "--engine" in result.output
    assert "--ai" in result.output
    assert "--store" in result.output


def test_root_help_is_recursive():
    """Root --help expands every subcommand and all their CLI options."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.output
    # Top-level command summary is still present.
    for command in ("analyze", "export", "server", "config"):
        assert command in out
    # analyze options.
    for opt in (
        "--dump",
        "--sym",
        "--ai",
        "--store",
        "--save-config",
        "--log-severity",
        "--log-dir",
    ):
        assert opt in out, f"missing analyze option {opt}"
    # export options (distinct from analyze) prove its subparser was expanded.
    assert "--to-store" in out
    assert "--to-config" in out
    # server options.
    assert "--host" in out
    assert "--port" in out
    # Nested config subcommands and their arguments.
    assert "config show" in out
    assert "config set" in out
    assert "KEY VALUE" in out


def test_export_help():
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    assert "--store" in result.output
    assert "--to-store" in result.output


def test_analyze_help_lists_backend_flags():
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--code-provider" in result.output
    assert "--repo" in result.output
    assert "--log-provider" in result.output
    assert "--log-service" in result.output


# ---------------------------------------------------------------------------
# Code / Log backend wiring
# ---------------------------------------------------------------------------


def test_repo_flag_enables_git_code_backend(tmp_path: Path):
    captured: dict[str, object] = {}

    async def mock_run(self, source):  # type: ignore[override]
        return _report()

    def _capture_code(settings):  # type: ignore[no-untyped-def]
        captured["enabled"] = settings.enabled
        captured["provider"] = settings.provider
        captured["repo_path"] = settings.repo_path
        return None

    with (
        mock.patch(_MOCK_RUN, mock_run),
        mock.patch("aegis_swr.backends.code.create_code_backend", _capture_code),
    ):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--repo",
                str(tmp_path),
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["enabled"] is True
    assert captured["provider"] == "git"
    assert captured["repo_path"] == str(tmp_path)


def test_log_service_sets_metadata(tmp_path: Path):
    captured: dict[str, object] = {}

    async def mock_run(self, source):  # type: ignore[override]
        captured["service"] = source.metadata.get("service")
        return _report()

    with mock.patch(_MOCK_RUN, mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--log-service",
                "auth-api",
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["service"] == "auth-api"


# ---------------------------------------------------------------------------
# --save-config
# ---------------------------------------------------------------------------


def test_save_config_writes_json(tmp_path: Path):
    config_file = tmp_path / "analyze.json"
    result = runner.invoke(
        app,
        [
            "analyze",
            "--ai",
            "openai",
            "--store",
            "sqlite",
            "--save-config",
            "--config",
            str(config_file),
        ],
    )
    assert result.exit_code == 0
    assert config_file.exists()
    data = json.loads(config_file.read_text())
    assert data["backends"]["ai"]["provider"] == "openai"
    assert data["store"] == "sqlite"


def test_save_config_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_file = tmp_path / "analyze.json"
    monkeypatch.setattr("aegis_swr.cli._config.DEFAULT_CONFIG_PATH", config_file)
    monkeypatch.setattr("aegis_swr.cli.commands.DEFAULT_CONFIG_PATH", config_file)
    result = runner.invoke(app, ["analyze", "--ai", "openai", "--save-config"])
    assert result.exit_code == 0
    assert config_file.exists()


# ---------------------------------------------------------------------------
# JSON config file loading and merge
# ---------------------------------------------------------------------------


def test_config_file_sets_defaults(tmp_path: Path):
    config_file = tmp_path / "cfg.json"
    config_file.write_text(
        json.dumps({"backends": {"ai": {"provider": "openai"}}, "output": "json"})
    )

    async def mock_run(self, source):  # type: ignore[override]
        return _report()

    with (
        mock.patch(_MOCK_RUN, mock_run),
        mock.patch("aegis_swr.backends.ai.create_ai_backend") as mock_ai,
    ):
        mock_ai.return_value = mock.MagicMock()
        mock_ai.return_value.model_name = "test"
        runner.invoke(
            app,
            [
                "analyze",
                "--config",
                str(config_file),
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path),
            ],
        )
    # The config file set ai=openai; we check the AISettings passed to create_ai_backend
    call_args = mock_ai.call_args
    assert call_args is not None
    settings_arg = call_args[0][0]
    assert settings_arg.provider == "openai"


def test_cli_reads_settings_from_config_asset(tmp_path: Path):
    """A config.json fixture is read and applied end-to-end through the CLI."""
    captured: dict[str, object] = {}

    async def mock_run(self, source):  # type: ignore[override]
        captured["logs"] = list(source.log_paths)
        return _report()

    asset = Path(__file__).parent / "fixtures" / "test_config-02.json"
    with mock.patch(_MOCK_RUN, mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--config",
                str(asset),
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    # The log paths declared in config.json flowed into the IncidentSource.
    assert captured["logs"] == ["C:/logs/app.log", "C:/logs/render.log"]


def test_cli_flag_overrides_config_file(tmp_path: Path):
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps({"ai": "openai"}))

    async def mock_run(self, source):  # type: ignore[override]
        return _report()

    with (
        mock.patch(_MOCK_RUN, mock_run),
        mock.patch("aegis_swr.backends.ai.create_ai_backend") as mock_ai,
    ):
        mock_ai.return_value = mock.MagicMock()
        mock_ai.return_value.model_name = "test"
        runner.invoke(
            app,
            [
                "analyze",
                "--config",
                str(config_file),
                "--ai",
                "anthropic",  # explicit flag overrides JSON value
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path),
            ],
        )
    settings_arg = mock_ai.call_args[0][0]
    assert settings_arg.provider == "anthropic"


def test_config_nested_ingest_service_reaches_metadata(tmp_path: Path):
    """A config.json in the new nested layout flows end-to-end through the CLI.

    The log-subsystem split (plan Part III) moves the log source under
    ``ingest.log_source``; the service name must still reach
    ``IncidentSource.metadata["service"]`` for the Data Adapter Stage 4 query.
    """
    captured: dict[str, object] = {}

    async def mock_run(self, source):  # type: ignore[override]
        captured["service"] = source.metadata.get("service")
        return _report()

    config_file = tmp_path / "cfg.json"
    config_file.write_text(
        json.dumps(
            {
                "ingest": {"log_source": {"provider": "file", "service": "billing-api"}},
                "logging": {"severity": "INFO"},
                "evidence": {"severity": "INFO"},
                "process": {"severity": "INFO"},
            }
        )
    )

    with mock.patch(_MOCK_RUN, mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--config",
                str(config_file),
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["service"] == "billing-api"


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_analyze_json_output(tmp_path: Path):
    report = _report()

    # json/rich output drives the domain-event stream (live display goes to
    # stderr); the stream must end with a completion event carrying the report.
    from aegis_swr.core.events import InvestigationCompleted

    async def mock_stream_events(self, source):  # type: ignore[override]
        yield InvestigationCompleted(report=report)

    with mock.patch(_MOCK_STREAM_EVENTS, mock_stream_events):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--output",
                "json",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path),
            ],
        )

    assert result.exit_code == 0
    # The full report is written exclusively to the result file; stdout carries
    # only a machine-readable locator (never the report body).
    parsed = json.loads(result.stdout)
    assert parsed["incident_id"]
    assert parsed["status"] == "complete"
    assert parsed["report_path"].endswith(f"{parsed['incident_id']}.json")
    assert "UAF in serialize()" not in result.stdout


def test_analyze_hitl_exits_nonzero(tmp_path: Path):
    report = _report(with_hitl=True)

    async def mock_run(self, source):  # type: ignore[override]
        return report

    with mock.patch(_MOCK_RUN, mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path),
            ],
        )

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# config show / set
# ---------------------------------------------------------------------------


def test_config_show_redacts_secrets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-supersecret")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "sk-ant-supersecret" not in result.output
    assert "***" in result.output


def test_config_set_writes_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    json_path = tmp_path / "config.json"
    json_path.write_text('{"backends": {"ai": {"provider": "anthropic"}}}')
    monkeypatch.setattr("aegis_swr.cli.commands.DEFAULT_CONFIG_PATH", json_path)
    result = runner.invoke(app, ["config", "set", "backends.ai.provider", "openai"])
    assert result.exit_code == 0
    data = json.loads(json_path.read_text())
    assert data["backends"]["ai"]["provider"] == "openai"


# ---------------------------------------------------------------------------
# _config helpers
# ---------------------------------------------------------------------------


def test_load_analyze_config_missing_file(tmp_path: Path):
    assert load_analyze_config(tmp_path / "nonexistent.json") == {}


def test_load_analyze_config_malformed(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    assert load_analyze_config(bad) == {}


def test_save_and_reload_config(tmp_path: Path):
    path = tmp_path / "cfg.json"
    save_analyze_config({"engine": "cdb", "dump": "/x.dmp"}, path)
    loaded = load_analyze_config(path)
    assert loaded["engine"] == "cdb"
    assert loaded["dump"] == "/x.dmp"


# ---------------------------------------------------------------------------
# Logging channels: validation + independent wiring (log-subsystem Phase C)
# ---------------------------------------------------------------------------


def test_evidence_severity_rejects_non_stream_level(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "analyze",
            "--evidence-severity",
            "DEBUG",  # only INFO|TRACE allowed for evidence
            "--output",
            "quiet",
            "--store",
            "filesystem",
            "--store-config",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2, result.output
    assert "--evidence-severity must be INFO or TRACE" in result.output


def test_process_severity_rejects_non_stream_level(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "analyze",
            "--process-severity",
            "WARNING",
            "--output",
            "quiet",
            "--store",
            "filesystem",
            "--store-config",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2, result.output
    assert "--process-severity must be INFO or TRACE" in result.output


def test_log_sink_rejects_unknown_value(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "analyze",
            "--log-sink",
            "kafka",
            "--output",
            "quiet",
            "--store",
            "filesystem",
            "--store-config",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2, result.output
    assert "--log-sink must be one of file, elk, fluent" in result.output


def test_evidence_and_process_severity_thread_independently(tmp_path: Path):
    """Each war-room channel is sourced from its own flag, not from --log-severity."""
    captured: dict[str, object] = {}

    async def fake_stream(orch, source, console, *, evidence_level, process_level, **_):
        captured["evidence"] = evidence_level
        captured["process"] = process_level
        return _report()

    with mock.patch("aegis_swr.cli.commands.stream_and_display", fake_stream):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--evidence-severity",
                "TRACE",
                "--process-severity",
                "INFO",
                "--log-severity",
                "ERROR",  # application channel - must not leak in
                "--output",
                "json",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured == {"evidence": "TRACE", "process": "INFO"}


def test_log_sink_is_wired_to_configure_logging(tmp_path: Path):
    """--log-sink reaches configure_logging, which owns the warn+fallback for stubs."""

    async def mock_run(self, source):  # type: ignore[override]
        return _report()

    with (
        mock.patch(_MOCK_RUN, mock_run),
        mock.patch("aegis_swr.cli.commands.configure_logging") as mock_cfg,
    ):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--log-sink",
                "elk",
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    # The effective (post-merge) re-apply call carries the selected sink.
    sinks = [call.kwargs.get("sink") for call in mock_cfg.call_args_list]
    assert "elk" in sinks


def test_evidence_persist_quiet_mode_warns(tmp_path: Path):
    """--evidence-persist with --output quiet has nothing to persist → warns."""

    async def mock_run(self, source):  # type: ignore[override]
        return _report()

    with (
        mock.patch(_MOCK_RUN, mock_run),
        mock.patch("aegis_swr.cli.commands.logger") as mock_logger,
    ):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--evidence-persist",
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    assert any("evidence-persist" in str(call.args) for call in mock_logger.warning.call_args_list)


def test_evidence_persist_is_wired_to_stream_and_display(tmp_path: Path):
    """--evidence-persist reaches stream_and_display with a resolved evidence dir."""
    captured: dict[str, object] = {}

    async def fake_stream(orch, source, console, *, evidence_persist, evidence_dir, **_):
        captured["persist"] = evidence_persist
        captured["dir"] = evidence_dir
        return _report()

    with mock.patch("aegis_swr.cli.commands.stream_and_display", fake_stream):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--evidence-persist",
                "--output",
                "json",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["persist"] is True
    assert captured["dir"]  # resolved to the default evidence dir
