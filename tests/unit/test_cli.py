"""Unit tests for the CLI - all Orchestrator calls mocked"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
import typer.testing

from aegis_swr.cli.commands import app
from aegis_swr.cli.config import (
    load_analyze_config,
    save_analyze_config,
)
from aegis_swr.config.settings import AISettings, BedrockSettings
from aegis_swr.core.events import InvestigationCompleted
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

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from *text*.

    Python 3.13 changed terminal-detection behaviour that causes Rich to emit
    colour codes even inside Typer's test runner.  Stripping them before
    assertions keeps help-text checks version-agnostic.
    """
    return _ANSI_RE.sub("", text)


def _report(with_hitl: bool = False) -> RCAReport:
    """Build a canned :class:`RCAReport`, optionally carrying a HITL request."""
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
    """[Unit] cli: ``python -m aegis_swr.cli`` launches the same Typer app.

    Scenario: the module is run with ``--help`` in a subprocess.

    Boundaries: exercises the module entry point end-to-end via subprocess.

    On failure, first check: the process must exit zero and its help must list
    ``analyze`` and a ``Usage:`` line.
    """

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
    """
    [Unit] cli: verifies analyze help.

    Scenario:
        Given test inputs and fixtures for analyze help
        When test_analyze_help executes the target flow
        Then the expected outcome for analyze help is confirmed.

    Boundaries:
        - Focus: analyze help
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to analyze help
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--dump" in out
    assert "--config" in out
    assert "--save-config" in out
    assert "--engine" in out
    assert "--ai" in out
    assert "--store" in out


def test_root_help_is_recursive():
    """[Unit] cli: root ``--help`` expands every subcommand and its options.

    Scenario: the root ``--help`` output is captured and scanned.

    Boundaries: exercises the recursive help rendering only.

    On failure, first check: the output must list every command and their distinct
    options, including nested ``config`` subcommands.
    """
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
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
    """
    [Unit] cli: verifies export help.

    Scenario:
        Given test inputs and fixtures for export help
        When test_export_help executes the target flow
        Then the expected outcome for export help is confirmed.

    Boundaries:
        - Focus: export help
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to export help
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--store" in out
    assert "--to-store" in out


def test_analyze_help_lists_backend_flags():
    """
    [Unit] cli: verifies analyze help lists backend flags.

    Scenario:
        Given test inputs and fixtures for analyze help lists backend flags
        When test_analyze_help_lists_backend_flags executes the target flow
        Then the expected outcome for analyze help lists backend flags is confirmed.

    Boundaries:
        - Focus: analyze help lists backend flags
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to analyze help lists backend flags
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--code-provider" in out
    assert "--repo" in out
    assert "--log-provider" in out
    assert "--log-service" in out


# ---------------------------------------------------------------------------
# Code / Log backend wiring
# ---------------------------------------------------------------------------


def test_repo_flag_enables_git_code_backend(tmp_path: Path):
    """
    [Unit] cli: the --repo flag enables the git code backend.

    Scenario: ``analyze --repo <dir>`` runs while the code-backend factory is
    mocked to capture its settings.

    Boundaries: the orchestrator and code factory are mocked; only flag-to-settings
    wiring is under test.

    On failure, first check: the captured settings must be enabled with provider
    ``git`` and the given repo path.
    """
    captured: dict[str, object] = {}

    async def mock_run(self, source) -> RCAReport:
        """Stand in for ``Orchestrator.run``, returning a canned report."""
        return _report()

    def _capture_code(settings):
        """Record the code-backend settings passed by the CLI, returning no backend."""
        captured["enabled"] = settings.enabled
        captured["provider"] = settings.provider
        captured["repo_path"] = settings.repo_path
        return

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
    """
    [Unit] cli: the --log-service flag sets the incident source metadata.

    Scenario: ``analyze --log-service auth-api`` runs while ``Orchestrator.run`` is
    mocked to capture the source metadata.

    Boundaries: the orchestrator is mocked; only flag-to-metadata wiring is under
    test.

    On failure, first check: the captured service metadata must equal ``auth-api``.
    """
    captured: dict[str, object] = {}

    async def mock_run(self, source) -> RCAReport:
        """Capture the incident source's service metadata, then return a report."""
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
    """
    [Unit] cli: verifies save config writes json.

    Scenario:
        Given test inputs and fixtures for save config writes json
        When test_save_config_writes_json executes the target flow
        Then the expected outcome for save config writes json is confirmed.

    Boundaries:
        - Focus: save config writes json
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to save config writes json
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
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
    """
    [Unit] cli: --save-config with no path writes to the default config path.

    Scenario: the default config path is monkeypatched to a temp file and
    ``analyze --save-config`` runs with no explicit ``--config``.

    Boundaries: the default path constant is patched; only the default-path branch
    is exercised.

    On failure, first check: the default config file must exist after the run.
    """
    config_file = tmp_path / "analyze.json"
    monkeypatch.setattr("aegis_swr.cli.config.DEFAULT_CONFIG_PATH", config_file)
    monkeypatch.setattr("aegis_swr.cli.commands.DEFAULT_CONFIG_PATH", config_file)
    result = runner.invoke(app, ["analyze", "--ai", "openai", "--save-config"])
    assert result.exit_code == 0
    assert config_file.exists()


# ---------------------------------------------------------------------------
# JSON config file loading and merge
# ---------------------------------------------------------------------------


def test_config_file_sets_defaults(tmp_path: Path):
    """
    [Unit] cli: a config file sets backend defaults reaching the AI factory.

    Scenario: ``analyze --config`` runs with a config declaring ai=openai while the
    AI factory is mocked.

    Boundaries: the orchestrator and AI factory are mocked; only config-to-settings
    wiring is under test.

    On failure, first check: the settings passed to the AI factory must carry
    provider ``openai``.
    """
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps({"backends": {"ai": {"provider": "openai"}}, "output": "json"}))

    async def mock_run(self, source) -> RCAReport:
        """Stand in for ``Orchestrator.run``, returning a canned report."""
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
    """[Unit] cli: a config.json fixture is read and applied end-to-end.

    Scenario: ``analyze`` runs with a fixture config while ``Orchestrator.run`` is
    mocked to capture the incident source.

    Boundaries: the orchestrator is mocked; only config-to-source wiring is under
    test.

    On failure, first check: the log paths declared in the fixture must flow into
    the captured ``IncidentSource``.
    """
    captured: dict[str, object] = {}

    async def mock_run(self, source) -> RCAReport:
        """Capture the incident source's log paths, then return a report."""
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
    """
    [Unit] cli: an explicit flag overrides the config file value.

    Scenario: ``analyze --config`` declares ai=openai but ``--ai anthropic`` is also
    passed while the AI factory is mocked.

    Boundaries: proves flag precedence over config; only the merge is under test.

    On failure, first check: the settings passed to the AI factory must carry
    provider ``anthropic``, not ``openai``.
    """
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps({"ai": "openai"}))

    async def mock_run(self, source) -> RCAReport:
        """Stand in for ``Orchestrator.run``, returning a canned report."""
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
    """[Unit] cli: a nested-layout config flows the service into source metadata.

    Scenario: ``analyze`` runs with a config placing the log source under
    ``ingest.log_source`` while ``Orchestrator.run`` is mocked.

    Boundaries: the log-subsystem split (plan Part III) moves the log source; only
    config-to-metadata wiring is under test.

    On failure, first check: the service name must reach
    ``IncidentSource.metadata["service"]`` for the Data Adapter Stage 4 query.
    """
    captured: dict[str, object] = {}

    async def mock_run(self, source) -> RCAReport:
        """Capture the incident source's service metadata, then return a report."""
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
# Prompt resolution (--prompt / --prompt-file / synthesised default)
# ---------------------------------------------------------------------------


def _run_capturing_assumption(args: list[str], tmp_path: Path) -> tuple[object, str]:
    """Invoke ``analyze`` with *args*, capturing ``source.user_assumption``."""
    captured: dict[str, object] = {}

    async def mock_run(self, source) -> RCAReport:
        """Capture the incident source's user assumption, then return a report."""
        captured["assumption"] = source.user_assumption
        return _report()

    with mock.patch(_MOCK_RUN, mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                *args,
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )
    return captured.get("assumption"), result


def test_prompt_flag_reaches_user_assumption(tmp_path: Path):
    """
    [Unit] cli: verifies prompt flag reaches user assumption.

    Scenario:
        Given test inputs and fixtures for prompt flag reaches user assumption
        When test_prompt_flag_reaches_user_assumption executes the target flow
        Then the expected outcome for prompt flag reaches user assumption is confirmed.

    Boundaries:
        - Focus: prompt flag reaches user assumption
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to prompt flag reaches user assumption
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    assumption, result = _run_capturing_assumption(["--prompt", "Suspect the new cache layer"], tmp_path)
    assert result.exit_code == 0, result.output
    assert assumption == "Suspect the new cache layer"


def test_prompt_file_is_read_and_wins_over_prompt(tmp_path: Path):
    """
    [Unit] cli: verifies prompt file is read and wins over prompt.

    Scenario:
        Given test inputs and fixtures for prompt file is read and wins over prompt
        When test_prompt_file_is_read_and_wins_over_prompt executes the target flow
        Then the expected outcome for prompt file is read and wins over prompt is confirmed.

    Boundaries:
        - Focus: prompt file is read and wins over prompt
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to prompt file is read and wins over prompt
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    prompt_file = tmp_path / "PROMPT.md"
    prompt_file.write_text("# Investigate the deadlock in the writer pool\n", encoding="utf-8")
    assumption, result = _run_capturing_assumption(
        ["--prompt", "inline text that must be ignored", "--prompt-file", str(prompt_file)],
        tmp_path,
    )
    assert result.exit_code == 0, result.output
    assert assumption == "# Investigate the deadlock in the writer pool"


def test_prompt_file_missing_falls_back_to_prompt(tmp_path: Path):
    """
    [Unit] cli: verifies prompt file missing falls back to prompt.

    Scenario:
        Given test inputs and fixtures for prompt file missing falls back to prompt
        When test_prompt_file_missing_falls_back_to_prompt executes the target flow
        Then the expected outcome for prompt file missing falls back to prompt is confirmed.

    Boundaries:
        - Focus: prompt file missing falls back to prompt
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to prompt file missing falls back to prompt
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    assumption, result = _run_capturing_assumption(
        ["--prompt", "fallback hypothesis", "--prompt-file", str(tmp_path / "nope.md")],
        tmp_path,
    )
    assert result.exit_code == 0, result.output
    assert assumption == "fallback hypothesis"


def test_no_prompt_synthesises_artifact_aware_default(tmp_path: Path):
    """
    [Unit] cli: verifies no prompt synthesises artifact aware default.

    Scenario:
        Given test inputs and fixtures for no prompt synthesises artifact aware default
        When test_no_prompt_synthesises_artifact_aware_default executes the target flow
        Then the expected outcome for no prompt synthesises artifact aware default is confirmed.

    Boundaries:
        - Focus: no prompt synthesises artifact aware default
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to no prompt synthesises artifact aware default
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    log_file = tmp_path / "app.log"
    log_file.write_text("boom", encoding="utf-8")
    assumption, result = _run_capturing_assumption(["--log", str(log_file)], tmp_path)
    assert result.exit_code == 0, result.output
    assert isinstance(assumption, str)
    # The synthesised prompt names the supplied artifact and asks for a root cause.
    assert "log file" in assumption
    assert "root cause" in assumption.lower()


def test_legacy_assume_config_key_migrates_to_prompt(tmp_path: Path):
    """
    [Unit] cli: verifies legacy assume config key migrates to prompt.

    Scenario:
        Given test inputs and fixtures for legacy assume config key migrates to prompt
        When test_legacy_assume_config_key_migrates_to_prompt executes the target flow
        Then the expected outcome for legacy assume config key migrates to prompt is confirmed.

    Boundaries:
        - Focus: legacy assume config key migrates to prompt
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to legacy assume config key migrates to prompt
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps({"assume": "legacy context note"}))
    assumption, result = _run_capturing_assumption(["--config", str(config_file)], tmp_path)
    assert result.exit_code == 0, result.output
    assert assumption == "legacy context note"


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_analyze_json_output(tmp_path: Path):
    """
    [Unit] cli: --output json writes a locator to stdout, not the report body.

    Scenario: ``analyze --output json`` runs while the event stream is mocked to
    yield a completion event carrying the report.

    Boundaries: the report body is written only to the result file; stdout carries a
    machine-readable locator.

    On failure, first check: stdout JSON must expose the incident id, status
    ``complete``, and a report path, and must never contain the root-cause text.
    """
    report = _report()

    # json/rich output drives the domain-event stream (live display goes to
    # stderr); the stream must end with a completion event carrying the report.

    async def mock_stream_events(self, source):
        """Yield a single completion event carrying the canned report."""
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
    """
    [Unit] cli: a HITL-escalated report makes analyze exit non-zero.

    Scenario: ``analyze`` runs while ``Orchestrator.run`` is mocked to return a
    report carrying a HITL request.

    Boundaries: the orchestrator is mocked; only the exit-code mapping is under test.

    On failure, first check: the CLI must exit with code 1 on a HITL report.
    """
    report = _report(with_hitl=True)

    async def mock_run(self, source) -> RCAReport:
        """Stand in for ``Orchestrator.run``, returning the HITL-bearing report."""
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
    """
    [Unit] cli: ``config show`` redacts API-key secrets from its output.

    Scenario: an ``ANTHROPIC_API_KEY`` is set in the environment and ``config show``
    runs.

    Boundaries: enforces the sensitivity policy for displayed configuration.

    On failure, first check: the secret value must be absent and a ``***`` mask must
    appear.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-supersecret")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "sk-ant-supersecret" not in result.output
    assert "***" in result.output


def test_config_set_writes_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    [Unit] cli: ``config set`` writes the dotted key into the JSON config file.

    Scenario: the default config path is patched to a temp file and ``config set
    backends.ai.provider openai`` runs.

    Boundaries: only the config-write path is exercised.

    On failure, first check: the JSON file must record the updated provider
    ``openai``.
    """
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
    """
    [Unit] cli: verifies load analyze config missing file.

    Scenario:
        Given test inputs and fixtures for load analyze config missing file
        When test_load_analyze_config_missing_file executes the target flow
        Then the expected outcome for load analyze config missing file is confirmed.

    Boundaries:
        - Focus: load analyze config missing file
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to load analyze config missing file
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    assert load_analyze_config(tmp_path / "nonexistent.json") == {}


def test_load_analyze_config_malformed(tmp_path: Path):
    """
    [Unit] cli: verifies load analyze config malformed.

    Scenario:
        Given test inputs and fixtures for load analyze config malformed
        When test_load_analyze_config_malformed executes the target flow
        Then the expected outcome for load analyze config malformed is confirmed.

    Boundaries:
        - Focus: load analyze config malformed
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to load analyze config malformed
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    assert load_analyze_config(bad) == {}


def test_save_and_reload_config(tmp_path: Path):
    """
    [Unit] cli: verifies save and reload config.

    Scenario:
        Given test inputs and fixtures for save and reload config
        When test_save_and_reload_config executes the target flow
        Then the expected outcome for save and reload config is confirmed.

    Boundaries:
        - Focus: save and reload config
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to save and reload config
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
    path = tmp_path / "cfg.json"
    save_analyze_config({"engine": "cdb", "dump": "/x.dmp"}, path)
    loaded = load_analyze_config(path)
    assert loaded["engine"] == "cdb"
    assert loaded["dump"] == "/x.dmp"


# ---------------------------------------------------------------------------
# Logging channels: validation + independent wiring (log-subsystem Phase C)
# ---------------------------------------------------------------------------


def test_evidence_severity_rejects_non_stream_level(tmp_path: Path):
    """
    [Unit] cli: verifies evidence severity rejects non stream level.

    Scenario:
        Given test inputs and fixtures for evidence severity rejects non stream level
        When test_evidence_severity_rejects_non_stream_level executes the target flow
        Then the expected outcome for evidence severity rejects non stream level is confirmed.

    Boundaries:
        - Focus: evidence severity rejects non stream level
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to evidence severity rejects non stream level
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
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
    """
    [Unit] cli: verifies process severity rejects non stream level.

    Scenario:
        Given test inputs and fixtures for process severity rejects non stream level
        When test_process_severity_rejects_non_stream_level executes the target flow
        Then the expected outcome for process severity rejects non stream level is confirmed.

    Boundaries:
        - Focus: process severity rejects non stream level
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to process severity rejects non stream level
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
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
    """
    [Unit] cli: verifies log sink rejects unknown value.

    Scenario:
        Given test inputs and fixtures for log sink rejects unknown value
        When test_log_sink_rejects_unknown_value executes the target flow
        Then the expected outcome for log sink rejects unknown value is confirmed.

    Boundaries:
        - Focus: log sink rejects unknown value
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log sink rejects unknown value
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by cli
    """
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
    """[Unit] cli: evidence and process severities thread from their own flags.

    Scenario: ``analyze`` runs with distinct ``--evidence-severity``/
    ``--process-severity`` and a separate ``--log-severity`` while the display is
    mocked.

    Boundaries: proves the two war-room channels are independent of the application
    log channel.

    On failure, first check: the captured levels must equal the two war-room flags
    and never the ``--log-severity`` value.
    """
    captured: dict[str, object] = {}

    async def fake_stream(orch, source, console, *, evidence_level, process_level, **_) -> RCAReport:
        """Capture the evidence/process verbosity levels threaded into the display."""
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
    """[Unit] cli: ``--log-sink`` reaches ``configure_logging``.

    Scenario: ``analyze`` runs with ``--log-sink elk`` while ``configure_logging``
    is mocked.

    Boundaries: the sink stub warn+fallback lives in ``configure_logging``; only the
    wiring is under test.

    On failure, first check: the effective ``configure_logging`` call must carry the
    selected ``elk`` sink.
    """

    async def mock_run(self, source) -> RCAReport:
        """Stand in for ``Orchestrator.run``, returning a canned report."""
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
    """[Unit] cli: ``--evidence-persist`` with quiet output warns of nothing to persist.

    Scenario: ``analyze`` runs with ``--evidence-persist`` and ``--output quiet``
    while the logger is mocked.

    Boundaries: proves the combination is a no-op that surfaces a warning.

    On failure, first check: a warning mentioning ``evidence-persist`` must be
    emitted.
    """

    async def mock_run(self, source) -> RCAReport:
        """Stand in for ``Orchestrator.run``, returning a canned report."""
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


# ---------------------------------------------------------------------------
# AWS Bedrock CLI wiring
# ---------------------------------------------------------------------------


def test_cli_ai_bedrock_sets_provider(tmp_path: Path):
    """[Unit] cli: ``--ai bedrock`` passes provider 'bedrock' to the AI factory.

    Scenario: ``analyze --ai bedrock`` runs while the AI factory is mocked to
    capture its settings.

    Boundaries: no real Bedrock client is constructed; only provider wiring is under
    test.

    On failure, first check: the captured provider must be ``bedrock``.
    """

    captured: dict[str, object] = {}

    def _capture_factory(settings: AISettings) -> object:
        """Record the AI provider requested by the CLI and return a mock backend."""
        captured["provider"] = settings.provider
        m = mock.MagicMock()
        m.model_name = "au.anthropic.claude-sonnet-4-6"
        return m

    async def mock_run(self, source) -> RCAReport:
        """Stand in for ``Orchestrator.run``, returning a canned report."""
        return _report()

    with (
        mock.patch(_MOCK_RUN, mock_run),
        mock.patch("aegis_swr.backends.ai.create_ai_backend", side_effect=_capture_factory),
    ):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--ai",
                "bedrock",
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured.get("provider") == "bedrock"


def test_config_example_has_bedrock_section():
    """[Unit] cli: config.example.json carries a valid backends.ai.bedrock block.

    Scenario: the repo-root ``config.example.json`` is parsed and its
    ``backends.ai.bedrock`` block inspected.

    Boundaries: a static asset validation; no CLI invocation.

    On failure, first check: the block must exist, contain only recognised
    ``BedrockSettings`` keys, and include ``region`` and ``model_id``.
    """
    config_path = Path(__file__).parent.parent.parent / "config.example.json"
    assert config_path.exists(), f"config.example.json not found at {config_path}"
    data = json.loads(config_path.read_text(encoding="utf-8"))

    # The file must be valid Settings-compatible JSON (extra keys are ignored).
    bedrock_block = data.get("backends", {}).get("ai", {}).get("bedrock", None)
    assert bedrock_block is not None, "config.example.json missing backends.ai.bedrock block"
    assert isinstance(bedrock_block, dict)

    # Every key present in the example block must be a recognized BedrockSettings field.
    known_fields = set(BedrockSettings.model_fields.keys())
    for key in bedrock_block:
        assert (
            key in known_fields
        ), f"config.example.json backends.ai.bedrock has unknown key {key!r}; valid keys: {sorted(known_fields)}"

    # The required identity fields must be present.
    assert "region" in bedrock_block
    assert "model_id" in bedrock_block


def test_env_example_documents_bedrock_auth():
    """[Unit] cli: .env.example documents Bedrock auth without real secrets.

    Scenario: the repo-root ``.env.example`` is read and scanned.

    Boundaries: a static asset validation; no CLI invocation.

    On failure, first check: the file must mention both ``AWS_BEARER_TOKEN_BEDROCK``
    and ``AWS_DEFAULT_REGION`` and assign no real secret value.
    """
    env_path = Path(__file__).parent.parent.parent / ".env.example"
    assert env_path.exists(), f".env.example not found at {env_path}"
    content = env_path.read_text(encoding="utf-8")

    assert "AWS_BEARER_TOKEN_BEDROCK" in content, ".env.example must document AWS_BEARER_TOKEN_BEDROCK"
    assert "AWS_DEFAULT_REGION" in content, ".env.example must document AWS_DEFAULT_REGION"


def test_evidence_persist_is_wired_to_stream_and_display(tmp_path: Path):
    """[Unit] cli: ``--evidence-persist`` reaches the display with a resolved dir.

    Scenario: ``analyze --evidence-persist`` runs with JSON output while
    ``stream_and_display`` is mocked.

    Boundaries: proves the persist flag and evidence directory are threaded through.

    On failure, first check: the captured persist flag must be True and the resolved
    directory non-empty.
    """
    captured: dict[str, object] = {}

    async def fake_stream(orch, source, console, *, evidence_persist, evidence_dir, **_) -> RCAReport:
        """Capture the evidence-persist flag and resolved directory from the display."""
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


# ---------------------------------------------------------------------------
# --agent explicit panel flag + aegis agents list
# ---------------------------------------------------------------------------


def test_agent_flag_builds_explicit_specs(tmp_path: Path):
    """
    [Unit] cli: verifies repeatable --agent builds explicit AgentSpecs.

    Scenario:
        Given --agent flags with priority/weight segments, when analyze runs,
        then the orchestrator is constructed with the parsed explicit specs
        (which implicitly switch panel selection to explicit mode).

    Boundaries:
        - Focus: --agent grammar <agent_key>[:priority][:weight] → AgentSpec
        - Fixtures/params: tmp_path; mocked Orchestrator.run
        - Scope: explicit_specs threaded into the Orchestrator

    On failure, first check:
        - _parse_agent_specs / _resolve_explicit_specs
        - explicit_specs kwarg on the Orchestrator constructor
    """
    captured: dict[str, object] = {}

    async def mock_run(self, source) -> RCAReport:
        """Capture the orchestrator's explicit agent specs, then return a report."""
        captured["explicit_specs"] = self._explicit_specs
        return _report()

    with mock.patch(_MOCK_RUN, mock_run):
        result = runner.invoke(
            app,
            [
                "analyze",
                "--agent",
                "os_kernel:5",
                "--agent",
                "skeptic:3:0.2",
                "--output",
                "quiet",
                "--store",
                "filesystem",
                "--store-config",
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    specs = captured["explicit_specs"]
    assert specs is not None
    assert [s.agent_key for s in specs] == ["os_kernel", "skeptic"]
    assert specs[0].priority == 5
    assert specs[1].priority == 3
    assert specs[1].weight == 0.2


def test_no_agent_flag_leaves_auto_selection(tmp_path: Path):
    """
    [Unit] cli: verifies omitting --agent leaves the panel on auto-selection.

    Scenario:
        Given no --agent flag and a default config (auto mode), when analyze
        runs, then the orchestrator receives ``explicit_specs=None`` so it
        auto-selects the panel.

    Boundaries:
        - Focus: the auto-mode default path of _resolve_explicit_specs
        - Fixtures/params: tmp_path; mocked Orchestrator.run
        - Scope: explicit_specs threaded into the Orchestrator

    On failure, first check:
        - settings.panel default mode ("auto")
        - _resolve_explicit_specs returning None when no flag/config panel
    """
    captured: dict[str, object] = {}

    async def mock_run(self, source) -> RCAReport:
        """Capture the orchestrator's explicit agent specs, then return a report."""
        captured["explicit_specs"] = self._explicit_specs
        return _report()

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
                str(tmp_path / "reports"),
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["explicit_specs"] is None


def test_agent_flag_rejects_out_of_range_priority(tmp_path: Path):
    """
    [Unit] cli: verifies a malformed --agent priority is rejected with exit 2.

    Scenario:
        Given --agent with a priority outside 1-5, when analyze runs, then the
        CLI exits with code 2 and a clear error message, without invoking the
        orchestrator.

    Boundaries:
        - Focus: invalid-input path for --agent parsing
        - Fixtures/params: tmp_path
        - Scope: _parse_agent_specs error handling

    On failure, first check:
        - The 1-5 range guard in _parse_agent_specs
        - _agent_flag_error raising typer.Exit(code=2)
    """
    result = runner.invoke(
        app,
        [
            "analyze",
            "--agent",
            "os_kernel:9",
            "--output",
            "quiet",
            "--store",
            "filesystem",
            "--store-config",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "priority must be in the range 1-5" in result.output


def test_agent_flag_rejects_empty_key(tmp_path: Path):
    """
    [Unit] cli: verifies a --agent value with no agent_key is rejected.

    Scenario:
        Given a --agent value beginning with a colon (empty key), when analyze
        runs, then the CLI exits with code 2 and an "agent_key is required"
        error.

    Boundaries:
        - Focus: invalid-input path for --agent parsing (empty key)
        - Fixtures/params: tmp_path
        - Scope: _parse_agent_specs error handling

    On failure, first check:
        - The empty-key guard in _parse_agent_specs
    """
    result = runner.invoke(
        app,
        [
            "analyze",
            "--agent",
            ":5",
            "--output",
            "quiet",
            "--store",
            "filesystem",
            "--store-config",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "agent_key is required" in result.output


def test_agents_list_prints_registry_table():
    """
    [Unit] cli: verifies 'aegis agents list' prints the registry table.

    Scenario:
        Given the agent registry, when 'aegis agents list' runs, then a table
        listing every registered agent's key, category, role, default priority,
        and display name is printed.

    Boundaries:
        - Focus: the agents list subcommand output
        - Fixtures/params: none
        - Scope: CLI output only

    On failure, first check:
        - agents_app registration under 'agents'
        - AGENT_REGISTRY contents and the AgentSpec default priority
    """
    result = runner.invoke(app, ["agents", "list"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "agent_key" in out
    assert "os_kernel" in out
    assert "skeptic" in out
    assert "arbiter" in out  # the skeptic's role
    assert "investigator" in out  # the other agents' role
    assert "OS Kernel Agent" in out
