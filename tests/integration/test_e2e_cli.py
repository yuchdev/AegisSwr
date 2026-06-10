"""E2E integration test: runs `aegis analyze` in-process with mocked Orchestrator"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import typer.testing

from aegis_swr.cli.commands import app
from aegis_swr.core.schemas import (
    ConfidenceLevel,
    Hypothesis,
    IncidentMode,
    RCAReport,
)

runner = typer.testing.CliRunner()

_MOCK_RUN = "aegis_swr.core.orchestrator.Orchestrator.run"


def _make_report() -> RCAReport:
    return RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        dump_hash="sha256:aabbcc",
        root_cause="Race condition in serialize() exposes use-after-free.",
        faulting_module="db_writer",
        faulting_function="db_writer::serialize",
        confidence_score=0.91,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(
            root_cause="Race condition exposes UAF",
            faulting_module="db_writer",
            confidence=0.91,
        ),
        consensus_rounds=1,
        mitigation_instructions=["Increase DB write timeout.", "Deploy hotfix."],
    )


def _write_dump(tmp_path: Path) -> Path:
    dump = tmp_path / "crash.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 64)
    return dump


async def _mock_run(self: object, source: object) -> RCAReport:  # type: ignore[override]
    return _make_report()


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def test_e2e_analyze_json_output(tmp_path: Path):
    dump = _write_dump(tmp_path)
    with mock.patch(_MOCK_RUN, _mock_run):
        result = runner.invoke(app, [
            "analyze",
            "--dump", str(dump),
            "--output", "json",
            "--store", "filesystem",
            "--store-config", str(tmp_path / "reports"),
        ])

    assert result.exit_code == 0, result.output
    # stdout carries only the locator; the report body lives in the result file.
    data = json.loads(result.output)
    assert data["incident_id"]
    assert data["status"] == "complete"
    assert data["report_path"].endswith(f"{data['incident_id']}.json")
    assert "Race condition" not in result.output


def test_e2e_analyze_json_full_output(tmp_path: Path):
    dump = _write_dump(tmp_path)
    with mock.patch(_MOCK_RUN, _mock_run):
        result = runner.invoke(app, [
            "analyze",
            "--dump", str(dump),
            "--output", "json-full",
            "--store", "filesystem",
            "--store-config", str(tmp_path / "reports"),
        ])

    assert result.exit_code == 0, result.output
    # json-full dumps the complete report body to stdout instead of a locator.
    data = json.loads(result.output)
    assert data["incident_id"]
    assert data["root_cause"] == "Race condition in serialize() exposes use-after-free."
    assert "primary_hypothesis" in data
    assert "agent_dialogue" in data
    # It is the report itself, not the locator wrapper.
    assert "report_path" not in data


# ---------------------------------------------------------------------------
# Rich output
# ---------------------------------------------------------------------------


def test_e2e_analyze_rich_output(tmp_path: Path):
    dump = _write_dump(tmp_path)
    with mock.patch(_MOCK_RUN, _mock_run):
        result = runner.invoke(app, [
            "analyze",
            "--dump", str(dump),
            "--output", "rich",
            "--store", "filesystem",
            "--store-config", str(tmp_path / "reports"),
        ])

    assert result.exit_code == 0
    assert "Race condition" in result.output
    # The verdict is shown, then a pointer to the saved result file.  A short
    # incident-id record is stamped inside the frame, but the full report JSON
    # (hypotheses, dialogue, …) is never dumped to stdout.
    assert "Report saved:" in result.output
    assert '"incident_id"' in result.output
    assert '"primary_hypothesis"' not in result.output
    assert '"agent_dialogue"' not in result.output


# ---------------------------------------------------------------------------
# Log-forensics mode (no dump)
# ---------------------------------------------------------------------------


def test_e2e_analyze_log_only_mode(tmp_path: Path):
    log_file = tmp_path / "app.log"
    log_file.write_text("2026-05-30T14:02:11 FATAL unhandled exception\n")

    async def _log_run(self: object, source: object) -> RCAReport:  # type: ignore[override]
        rep = _make_report()
        return rep.model_copy(update={"mode": IncidentMode.LOG_FORENSICS, "dump_hash": None})

    with mock.patch(_MOCK_RUN, _log_run):
        result = runner.invoke(app, [
            "analyze",
            "--log", str(log_file),
            "--output", "json",
            "--store", "filesystem",
            "--store-config", str(tmp_path / "reports"),
        ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["mode"] == "log_forensics"


# ---------------------------------------------------------------------------
# Config file round-trip in E2E context
# ---------------------------------------------------------------------------


def test_e2e_config_roundtrip(tmp_path: Path):
    """Save options to JSON config, reload them, run with the stored values"""
    dump = _write_dump(tmp_path)
    config_file = tmp_path / "cfg.json"

    # Step 1: save config.
    result = runner.invoke(app, [
        "analyze",
        "--dump", str(dump),
        "--ai", "openai",
        "--store", "filesystem",
        "--store-config", str(tmp_path / "reports"),
        "--save-config",
        "--config", str(config_file),
    ])
    assert result.exit_code == 0
    saved = json.loads(config_file.read_text())
    assert saved["ai"] == "openai"

    # Step 2: run using saved config (no --ai flag).

    async def _capturing_run(self: object, source: object) -> RCAReport:  # type: ignore[override]
        return _make_report()

    with mock.patch(_MOCK_RUN, _capturing_run):
        with mock.patch("aegis_swr.backends.ai.create_ai_backend") as mock_ai:
            mock_ai.return_value = mock.MagicMock()
            mock_ai.return_value.model_name = "test"
            runner.invoke(app, [
                "analyze",
                "--config", str(config_file),
                "--store", "filesystem",
                "--store-config", str(tmp_path / "reports"),
                "--output", "json",
            ])
        call_ai_settings = mock_ai.call_args[0][0]
        assert call_ai_settings.provider == "openai"
