"""Unit tests for the CLI — all Orchestrator calls mocked."""
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
        ) if with_hitl else None,
    )


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_analyze_help() -> None:
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--dump" in result.output
    assert "--config" in result.output
    assert "--save-config" in result.output
    assert "--engine" in result.output
    assert "--ai" in result.output
    assert "--store" in result.output


def test_export_help() -> None:
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    assert "--store" in result.output
    assert "--to-store" in result.output


# ---------------------------------------------------------------------------
# --save-config
# ---------------------------------------------------------------------------


def test_save_config_writes_json(tmp_path: Path) -> None:
    config_file = tmp_path / "analyze.json"
    result = runner.invoke(app, [
        "analyze",
        "--ai", "openai",
        "--store", "sqlite",
        "--save-config",
        "--config", str(config_file),
    ])
    assert result.exit_code == 0
    assert config_file.exists()
    data = json.loads(config_file.read_text())
    assert data["ai"] == "openai"
    assert data["store"] == "sqlite"


def test_save_config_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "analyze.json"
    monkeypatch.setattr("aegis_swr.cli._config.DEFAULT_CONFIG_PATH", config_file)
    monkeypatch.setattr("aegis_swr.cli.commands.DEFAULT_CONFIG_PATH", config_file)
    result = runner.invoke(app, ["analyze", "--ai", "openai", "--save-config"])
    assert result.exit_code == 0
    assert config_file.exists()


# ---------------------------------------------------------------------------
# JSON config file loading and merge
# ---------------------------------------------------------------------------


def test_config_file_sets_defaults(tmp_path: Path) -> None:
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps({"ai": "openai", "output": "json"}))


    async def mock_run(self, source):  # type: ignore[override]
        return _report()

    with (
        mock.patch(_MOCK_RUN, mock_run),
        mock.patch("aegis_swr.backends.ai.create_ai_backend") as mock_ai,
    ):
        mock_ai.return_value = mock.MagicMock()
        mock_ai.return_value.model_name = "test"
        runner.invoke(app, [
            "analyze",
            "--config", str(config_file),
            "--store", "filesystem",
            "--store-config", str(tmp_path),
        ])
    # The config file set ai=openai; we check the AISettings passed to create_ai_backend
    call_args = mock_ai.call_args
    assert call_args is not None
    settings_arg = call_args[0][0]
    assert settings_arg.provider == "openai"


def test_cli_flag_overrides_config_file(tmp_path: Path) -> None:
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
        runner.invoke(app, [
            "analyze",
            "--config", str(config_file),
            "--ai", "anthropic",         # explicit flag overrides JSON value
            "--store", "filesystem",
            "--store-config", str(tmp_path),
        ])
    settings_arg = mock_ai.call_args[0][0]
    assert settings_arg.provider == "anthropic"


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_analyze_json_output(tmp_path: Path) -> None:
    report = _report()

    async def mock_run(self, source):  # type: ignore[override]
        return report

    with mock.patch(_MOCK_RUN, mock_run):
        result = runner.invoke(app, [
            "analyze",
            "--output", "json",
            "--store", "filesystem",
            "--store-config", str(tmp_path),
        ])

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "incident_id" in parsed
    assert parsed["root_cause"] == "UAF in serialize()"


def test_analyze_hitl_exits_nonzero(tmp_path: Path) -> None:
    report = _report(with_hitl=True)

    async def mock_run(self, source):  # type: ignore[override]
        return report

    with mock.patch(_MOCK_RUN, mock_run):
        result = runner.invoke(app, [
            "analyze",
            "--output", "quiet",
            "--store", "filesystem",
            "--store-config", str(tmp_path),
        ])

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# config show / set
# ---------------------------------------------------------------------------


def test_config_show_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-supersecret")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "sk-ant-supersecret" not in result.output
    assert "***" in result.output


def test_config_set_writes_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("backends:\n  ai:\n    provider: anthropic\n")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["config", "set", "backends.ai.provider", "openai"])
    assert result.exit_code == 0
    import yaml
    data = yaml.safe_load(yaml_path.read_text())
    assert data["backends"]["ai"]["provider"] == "openai"


# ---------------------------------------------------------------------------
# _config helpers
# ---------------------------------------------------------------------------


def test_load_analyze_config_missing_file(tmp_path: Path) -> None:
    assert load_analyze_config(tmp_path / "nonexistent.json") == {}


def test_load_analyze_config_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    assert load_analyze_config(bad) == {}


def test_save_and_reload_config(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    save_analyze_config({"ai": "openai", "engine": "cdb", "dump": "/x.dmp"}, path)
    loaded = load_analyze_config(path)
    assert loaded["ai"] == "openai"
    assert loaded["engine"] == "cdb"
    assert loaded["dump"] == "/x.dmp"
