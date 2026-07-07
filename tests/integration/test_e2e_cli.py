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


async def _mock_run(self: object, source: object) -> RCAReport:
    return _make_report()


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def test_e2e_analyze_json_output(tmp_path: Path):
    """
    [E2E] e2e cli: verifies e2e analyze json output.

    Scenario:
        Given test inputs and fixtures for e2e analyze json output
        When test_e2e_analyze_json_output executes the target flow
        Then the expected outcome for e2e analyze json output is confirmed.

    Boundaries:
        - Focus: e2e analyze json output
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to e2e analyze json output
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by e2e cli
    """
    dump = _write_dump(tmp_path)
    with mock.patch(_MOCK_RUN, _mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--dump",
                str(dump),
                "--output",
                "json",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    # stdout carries only the locator; the report body lives in the result file.
    data = json.loads(result.stdout)
    assert data["incident_id"]
    assert data["status"] == "complete"
    assert data["report_path"].endswith(f"{data['incident_id']}.json")
    assert "Race condition" not in result.stdout


def test_e2e_analyze_json_full_output(tmp_path: Path):
    """
    [E2E] e2e cli: verifies e2e analyze json full output.

    Scenario:
        Given test inputs and fixtures for e2e analyze json full output
        When test_e2e_analyze_json_full_output executes the target flow
        Then the expected outcome for e2e analyze json full output is confirmed.

    Boundaries:
        - Focus: e2e analyze json full output
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to e2e analyze json full output
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by e2e cli
    """
    dump = _write_dump(tmp_path)
    with mock.patch(_MOCK_RUN, _mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--dump",
                str(dump),
                "--output",
                "json-full",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    # json-full dumps the complete report body to stdout instead of a locator.
    data = json.loads(result.stdout)
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
    """
    [E2E] e2e cli: verifies e2e analyze rich output.

    Scenario:
        Given test inputs and fixtures for e2e analyze rich output
        When test_e2e_analyze_rich_output executes the target flow
        Then the expected outcome for e2e analyze rich output is confirmed.

    Boundaries:
        - Focus: e2e analyze rich output
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to e2e analyze rich output
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by e2e cli
    """
    dump = _write_dump(tmp_path)
    with mock.patch(_MOCK_RUN, _mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--dump",
                str(dump),
                "--output",
                "rich",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

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
    """
    [E2E] e2e cli: verifies e2e analyze log only mode.

    Scenario:
        Given test inputs and fixtures for e2e analyze log only mode
        When test_e2e_analyze_log_only_mode executes the target flow
        Then the expected outcome for e2e analyze log only mode is confirmed.

    Boundaries:
        - Focus: e2e analyze log only mode
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to e2e analyze log only mode
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by e2e cli
    """
    log_file = tmp_path / "app.log"
    log_file.write_text("2026-05-30T14:02:11 FATAL unhandled exception\n")

    async def _log_run(self: object, source: object) -> RCAReport:
        rep = _make_report()
        return rep.model_copy(update={"mode": IncidentMode.LOG_FORENSICS, "dump_hash": None})

    with mock.patch(_MOCK_RUN, _log_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--log",
                str(log_file),
                "--output",
                "json",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["mode"] == "log_forensics"


# ---------------------------------------------------------------------------
# Config file round-trip in E2E context
# ---------------------------------------------------------------------------


def test_e2e_config_roundtrip(tmp_path: Path):
    """Save options to JSON config, reload them, run with the stored values"""
    dump = _write_dump(tmp_path)
    config_file = tmp_path / "cfg.json"

    # Step 1: save config.
    result = runner.invoke(
        app,
        [
            "analyze",
            "--dump",
            str(dump),
            "--ai",
            "openai",
            "--store",
            "filesystem",
            "--store-config",
            str(tmp_path / "reports"),
            "--save-config",
            "--config",
            str(config_file),
        ],
    )
    assert result.exit_code == 0
    saved = json.loads(config_file.read_text())
    assert saved["backends"]["ai"]["provider"] == "openai"

    # Step 2: run using saved config (no --ai flag).

    async def _capturing_run(self: object, source: object) -> RCAReport:
        return _make_report()

    with mock.patch(_MOCK_RUN, _capturing_run):
        with mock.patch("aegis_swr.backends.ai.create_ai_backend") as mock_ai:
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
                    str(tmp_path / "reports"),
                    "--output",
                    "json",
                ],
            )
        call_ai_settings = mock_ai.call_args[0][0]
        assert call_ai_settings.provider == "openai"


# ---------------------------------------------------------------------------
# Nested log sections (the log-subsystem split, plan Part III - Phase B)
# ---------------------------------------------------------------------------


def test_e2e_nested_log_sections_flow_through(tmp_path: Path):
    """A config.json using the new nested sections is consumed end-to-end."""
    config_file = tmp_path / "cfg.json"
    config_file.write_text(
        json.dumps(
            {
                "ingest": {"log_source": {"provider": "file", "service": "billing-api"}},
                "logging": {"severity": "INFO", "sink": "file"},
                "evidence": {"severity": "TRACE"},
                "process": {"severity": "INFO"},
            }
        )
    )
    captured: dict[str, object] = {}

    async def _capture(self: object, source: object) -> RCAReport:
        captured["service"] = source.metadata.get("service")  # type: ignore[attr-defined]
        return _make_report()

    log_file = tmp_path / "app.log"
    log_file.write_text("2026-05-30T14:02:11 FATAL boom\n")

    with mock.patch(_MOCK_RUN, _capture):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--log",
                str(log_file),
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


def test_e2e_save_config_writes_nested_sections(tmp_path: Path):
    """--save-config persists the log options into their nested sections."""
    dump = _write_dump(tmp_path)
    config_file = tmp_path / "cfg.json"
    result = runner.invoke(
        app,
        [
            "analyze",
            "--dump",
            str(dump),
            "--log-provider",
            "file",
            "--log-service",
            "billing-api",
            "--log-severity",
            "DEBUG",
            "--store",
            "filesystem",
            "--store-config",
            str(tmp_path / "reports"),
            "--save-config",
            "--config",
            str(config_file),
        ],
    )
    assert result.exit_code == 0, result.output
    saved = json.loads(config_file.read_text())
    # Log source and application severity land in their dotted sections …
    assert saved["ingest"]["log_source"]["service"] == "billing-api"
    assert saved["logging"]["severity"] == "DEBUG"
    # … and no flat log_* key leaks to the top level.
    assert "log_service" not in saved
    assert "log_severity" not in saved


# ---------------------------------------------------------------------------
# New CLI flags + validation (the log-subsystem split, plan Part III - Phase C)
# ---------------------------------------------------------------------------


def test_e2e_new_log_flags_persist_to_sections(tmp_path: Path):
    """The Phase-C flags are saved into their nested sections by --save-config."""
    dump = _write_dump(tmp_path)
    config_file = tmp_path / "cfg.json"
    result = runner.invoke(
        app,
        [
            "analyze",
            "--dump",
            str(dump),
            "--log-sink",
            "fluent",
            "--evidence-severity",
            "TRACE",
            "--process-severity",
            "TRACE",
            "--evidence-persist",
            "--store",
            "filesystem",
            "--store-config",
            str(tmp_path / "reports"),
            "--save-config",
            "--config",
            str(config_file),
        ],
    )
    assert result.exit_code == 0, result.output
    saved = json.loads(config_file.read_text())
    assert saved["logging"]["sink"] == "fluent"
    assert saved["evidence"]["severity"] == "TRACE"
    assert saved["evidence"]["persist"] is True
    assert saved["process"]["severity"] == "TRACE"


def test_e2e_invalid_value_from_config_file_is_rejected(tmp_path: Path):
    """Validation covers config.json values, not just CLI flags."""
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps({"evidence": {"severity": "DEBUG"}}))
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
    assert result.exit_code == 2, result.output
    assert "--evidence-severity must be INFO or TRACE" in result.output


# ---------------------------------------------------------------------------
# Application log sinks (the log-subsystem split, plan Part III - Phase E)
# ---------------------------------------------------------------------------


def test_e2e_elk_sink_falls_back_and_completes(tmp_path: Path):
    """A stub sink (elk) exercises the real configure_logging fallback path
    end-to-end without aborting the run (warn + fall back to file/stderr)."""
    dump = _write_dump(tmp_path)
    with mock.patch(_MOCK_RUN, _mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--dump",
                str(dump),
                "--log-sink",
                "elk",
                "--log-dir",
                str(tmp_path / "logs"),
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    # The fallback file sink was used, and it captured the stub-sink warning.
    log_file = tmp_path / "logs" / "aegis-swr.log"
    assert log_file.exists()
    assert "'elk' is not yet implemented" in log_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Evidence persistence (the log-subsystem split, plan Part III - Phase F)
# ---------------------------------------------------------------------------


def test_e2e_evidence_persist_writes_file(tmp_path: Path, monkeypatch):
    """End-to-end: --evidence-persist writes the Evidence Stream transcript.

    Drives the real war-room view + persistence by publishing domain events on
    the orchestrator's bus through a mocked ``stream_events``. Persistence is a
    WarRoomView feature (wide terminals), so force a >= 80 column width."""
    from aegis_swr.core.events import (
        EvidenceExtracted,
        InvestigationCompleted,
        InvestigationStarted,
    )

    monkeypatch.setenv("COLUMNS", "120")
    report = _make_report()
    dump = _write_dump(tmp_path)
    config_file = tmp_path / "cfg.json"
    config_file.write_text(
        json.dumps(
            {"evidence": {"severity": "TRACE", "persist": True, "dir": str(tmp_path / "ev")}}
        )
    )

    async def mock_stream_events(self, source):
        self.events.publish(
            InvestigationStarted(incident_id=str(report.incident_id), source=source)
        )
        self.events.publish(
            EvidenceExtracted(
                brief={"fault_class": "access_violation", "faulting_module": "db_writer"}
            )
        )
        self.events.publish(InvestigationCompleted(report=report))
        yield InvestigationCompleted(report=report)

    with mock.patch("aegis_swr.core.orchestrator.Orchestrator.stream_events", mock_stream_events):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--dump",
                str(dump),
                "--config",
                str(config_file),
                "--output",
                "json",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    path = tmp_path / "ev" / f"evidence-{report.incident_id}.log"
    assert path.exists()
    assert "ACCESS_VIOLATION" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Legacy config migration (the log-subsystem split, plan Part III - Phase J)
# ---------------------------------------------------------------------------


def test_e2e_legacy_logging_config_is_migrated(tmp_path: Path):
    """A pre-split config.json (single conflated `logging` section) still works:
    `logging.service` migrates to `ingest.log_source.service` and reaches metadata."""
    captured: dict[str, object] = {}

    async def capture(self: object, source: object) -> RCAReport:
        captured["service"] = source.metadata.get("service")  # type: ignore[attr-defined]
        return _make_report()

    config_file = tmp_path / "cfg.json"
    config_file.write_text(
        json.dumps({"logging": {"provider": "file", "service": "legacy-svc", "severity": "DEBUG"}})
    )
    log_file = tmp_path / "app.log"
    log_file.write_text("2026-05-30T14:02:11 FATAL boom\n")

    with mock.patch(_MOCK_RUN, capture):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--log",
                str(log_file),
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
    assert captured["service"] == "legacy-svc"


def test_e2e_malformed_config_warning_reaches_logfile(tmp_path: Path):
    """An unreadable/malformed config.json never aborts startup, and the warning
    is captured in the configured application log file (not just on stderr)."""
    bad_config = tmp_path / "cfg.json"
    bad_config.write_text("{not valid json")
    log_dir = tmp_path / "logs"
    dump = _write_dump(tmp_path)

    with mock.patch(_MOCK_RUN, _mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--dump",
                str(dump),
                "--config",
                str(bad_config),
                "--log-dir",
                str(log_dir),
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output  # defaults take over, no abort
    log_file = log_dir / "aegis-swr.log"
    assert log_file.exists()
    assert "Could not read config file" in log_file.read_text(encoding="utf-8")
